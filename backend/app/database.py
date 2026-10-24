from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from .config import settings

engine = create_engine(settings.database_url, connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def uid() -> str:
    return str(uuid4())


class Timestamped:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class User(Timestamped, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    projects: Mapped[list["ScoreProject"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class ScoreProject(Timestamped, Base):
    __tablename__ = "score_projects"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    source_filename: Mapped[str] = mapped_column(String(255))
    source_path: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(50), default="uploaded")
    recognition_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    musicxml_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    midi_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    user: Mapped[User] = relationship(back_populates="projects")
    practice_versions: Mapped[list["PracticeVersion"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    tasks: Mapped[list["ProcessingTask"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class PracticeVersion(Timestamped, Base):
    __tablename__ = "practice_versions"
    project_id: Mapped[str] = mapped_column(ForeignKey("score_projects.id"), index=True)
    semitone: Mapped[int] = mapped_column(Integer, default=0)
    tempo_bpm: Mapped[int] = mapped_column(Integer, default=72)
    loop_start_beat: Mapped[int | None] = mapped_column(Integer, nullable=True)
    loop_end_beat: Mapped[int | None] = mapped_column(Integer, nullable=True)
    project: Mapped[ScoreProject] = relationship(back_populates="practice_versions")
    assets: Mapped[list["AudioAsset"]] = relationship(back_populates="practice_version", cascade="all, delete-orphan")


class AudioAsset(Timestamped, Base):
    __tablename__ = "audio_assets"
    practice_version_id: Mapped[str] = mapped_column(ForeignKey("practice_versions.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30))  # accompaniment | melody_guide
    status: Mapped[str] = mapped_column(String(30), default="queued")
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    practice_version: Mapped[PracticeVersion] = relationship(back_populates="assets")


class ProcessingTask(Timestamped, Base):
    __tablename__ = "processing_tasks"
    project_id: Mapped[str] = mapped_column(ForeignKey("score_projects.id"), index=True)
    task_type: Mapped[str] = mapped_column(String(30))  # recognition | rendering
    status: Mapped[str] = mapped_column(String(30), default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(String(255), default="queued")
    project: Mapped[ScoreProject] = relationship(back_populates="tasks")
