from pathlib import Path
from uuid import uuid4

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import create_token, current_user, db_session, hash_password, verify_password
from .config import settings
from .database import AudioAsset, Base, PracticeVersion, ProcessingTask, ScoreProject, User, engine
from .providers import ProviderNotConfigured, omr_provider

app = FastAPI(title="声伴 API", version="0.1.0")


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class PracticeVersionInput(BaseModel):
    semitone: int = Field(default=0, ge=-12, le=12)
    tempo_bpm: int = Field(default=72, ge=30, le=220)
    loop_start_beat: int | None = Field(default=None, ge=0)
    loop_end_beat: int | None = Field(default=None, ge=0)


@app.on_event("startup")
def startup() -> None:
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "omr_provider": settings.omr_provider, "audio_renderer": settings.audio_renderer}


@app.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register(payload: Credentials, db: Session = Depends(db_session)) -> dict:
    if db.scalar(select(User).where(User.email == payload.email)):
        raise HTTPException(status_code=409, detail="该邮箱已注册")
    user = User(email=payload.email, password_hash=hash_password(payload.password))
    db.add(user); db.commit(); db.refresh(user)
    return {"access_token": create_token(user), "token_type": "bearer"}


@app.post("/auth/login")
def login(payload: Credentials, db: Session = Depends(db_session)) -> dict:
    user = db.scalar(select(User).where(User.email == payload.email))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    return {"access_token": create_token(user), "token_type": "bearer"}


def serialize_project(project: ScoreProject) -> dict:
    return {"id": project.id, "title": project.title, "source_filename": project.source_filename, "status": project.status, "recognition_note": project.recognition_note, "created_at": project.created_at}


def run_recognition(project_id: str) -> None:
    """队列接口：开发环境使用 BackgroundTasks，生产环境替换为 Celery/Cloud Tasks worker。"""
    from .database import SessionLocal
    db = SessionLocal()
    try:
        project = db.get(ScoreProject, project_id)
        task = db.scalar(select(ProcessingTask).where(ProcessingTask.project_id == project_id, ProcessingTask.task_type == "recognition"))
        if not project or not task:
            return
        task.status, task.progress, task.message = "running", 15, "正在读取乐谱图片"
        db.commit()
        try:
            result = omr_provider().recognize(Path(project.source_path))
        except ProviderNotConfigured as exc:
            project.status = "waiting_provider_config"
            project.recognition_note = str(exc)
            task.status, task.progress, task.message = "blocked", 0, "等待识谱服务配置"
            db.commit(); return
        musicxml_path = settings.storage_root / project.user_id / project.id / "score.musicxml"
        midi_path = settings.storage_root / project.user_id / project.id / "score.mid"
        musicxml_path.parent.mkdir(parents=True, exist_ok=True)
        musicxml_path.write_bytes(result.musicxml); midi_path.write_bytes(result.midi)
        project.musicxml_path, project.midi_path, project.status = str(musicxml_path), str(midi_path), "needs_review"
        task.status, task.progress, task.message = "completed", 100, "识谱完成，等待用户校对"
        db.commit()
    finally:
        db.close()


@app.post("/projects", status_code=status.HTTP_202_ACCEPTED)
async def create_project(
    background_tasks: BackgroundTasks,
    title: str = Form(..., min_length=1, max_length=255),
    copyright_confirmed: bool = Form(...),
    image: UploadFile = File(...),
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> dict:
    if not copyright_confirmed:
        raise HTTPException(status_code=422, detail="必须确认拥有乐谱练习使用权")
    if image.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(status_code=415, detail="仅支持 JPG、PNG、WEBP 乐谱图片")
    project_id = str(uuid4())
    suffix = Path(image.filename or "score.jpg").suffix.lower() or ".jpg"
    target = settings.storage_root / user.id / project_id / f"source{suffix}"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(await image.read())
    project = ScoreProject(id=project_id, user_id=user.id, title=title, source_filename=image.filename or target.name, source_path=str(target), status="queued")
    task = ProcessingTask(project_id=project_id, task_type="recognition", status="queued", message="等待识谱")
    db.add_all([project, task]); db.commit(); db.refresh(project)
    background_tasks.add_task(run_recognition, project_id)
    return {"project": serialize_project(project), "task_id": task.id}


@app.get("/projects")
def list_projects(user: User = Depends(current_user), db: Session = Depends(db_session)) -> list[dict]:
    return [serialize_project(project) for project in db.scalars(select(ScoreProject).where(ScoreProject.user_id == user.id).order_by(ScoreProject.created_at.desc()))]


def owned_project(project_id: str, user: User, db: Session) -> ScoreProject:
    project = db.get(ScoreProject, project_id)
    if not project or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="找不到该曲目")
    return project


@app.get("/projects/{project_id}")
def get_project(project_id: str, user: User = Depends(current_user), db: Session = Depends(db_session)) -> dict:
    project = owned_project(project_id, user, db)
    versions = [
        {
            "id": version.id,
            "semitone": version.semitone,
            "tempo_bpm": version.tempo_bpm,
            "assets": [{"id": asset.id, "kind": asset.kind, "status": asset.status} for asset in version.assets],
        }
        for version in project.practice_versions
    ]
    return {**serialize_project(project), "versions": versions}


@app.get("/tasks/{task_id}")
def get_task(task_id: str, user: User = Depends(current_user), db: Session = Depends(db_session)) -> dict:
    task = db.get(ProcessingTask, task_id)
    if not task or task.project.user_id != user.id:
        raise HTTPException(status_code=404, detail="找不到该任务")
    return {"id": task.id, "type": task.task_type, "status": task.status, "progress": task.progress, "message": task.message}


@app.post("/projects/{project_id}/versions", status_code=status.HTTP_201_CREATED)
def create_practice_version(project_id: str, payload: PracticeVersionInput, user: User = Depends(current_user), db: Session = Depends(db_session)) -> dict:
    project = owned_project(project_id, user, db)
    if project.status != "needs_review":
        raise HTTPException(status_code=409, detail="乐谱尚未识别完成，不能生成伴奏版本")
    version = PracticeVersion(project_id=project.id, **payload.model_dump())
    db.add(version); db.commit(); db.refresh(version)
    # 真实渲染器接入后在此创建 accompaniment、melody_guide 两个 AudioAsset 和渲染任务。
    return {"id": version.id, "status": "waiting_renderer_config"}
