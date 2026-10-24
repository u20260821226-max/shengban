# 声伴后端（可接入骨架）

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
2. 项目选择过 Audiveris 作为免费本地识谱候选，当前电脑已安装 Audiveris（含 Java）并用于手工准备曲目，但后端适配代码尚未接入，安装桌面工具不等于已实现自动识谱接口。
3. 将 `.env` 内的供应商名称、服务地址与密钥填入部署环境；密钥不能写入前端或提交到 Git。
4. 生产环境再将 `BackgroundTasks` 替换为持久化队列，并迁移 SQLite 与本地文件存储。
