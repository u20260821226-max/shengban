# 声伴后端

当前识谱服务为 `public_api.py` + `omr/`，部署方式见 [公网识谱部署](../docs/公网识谱部署.md)。匿名浏览器 token 隔离任务，无需注册；不代表实现正式用户系统。下文 `app/` 是独立的旧账户骨架，当前网站未使用。

另有独立的本机自动识谱测试：在项目根目录运行 `python3 -m backend.local_recognition`，打开 http://localhost:4175/ 。它使用标准库和 Pillow，不依赖下面的 FastAPI/账户骨架，不是公网生产服务。详见 `docs/自动识谱本机测试.md`。

## 已实现

- 邮箱注册、登录和 Bearer JWT 鉴权。
- 用户隔离的图片上传与本地私有存储。
- `ScoreProject`、`PracticeVersion`、`AudioAsset`、`ProcessingTask` SQLite 数据模型。
- 异步识谱任务状态与轮询 API。
- OMR/音频渲染供应商适配边界；未配置时将任务标为 `blocked` / `waiting_provider_config`，绝不生成伪造音频。

## 本地运行

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

打开 `http://127.0.0.1:8000/docs` 查看 API 文档。

## 当前限制与下一步

1. `app/providers.py` 尚未实现具体服务商。OMR 需返回 MusicXML 与 MIDI；音频渲染需返回实际音频文件。
2. `app/` 的供应商适配器尚未接入。实际 Audiveris 适配已实现在独立的 `omr/pipeline.py`，不要混淆两个入口。
3. 将 `.env` 内的供应商名称、服务地址与密钥填入部署环境；密钥不能写入前端或提交到 Git。
4. 生产环境再将 `BackgroundTasks` 替换为持久化队列，并迁移 SQLite 与本地文件存储。
