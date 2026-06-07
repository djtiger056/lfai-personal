# Codex 项目指令

必须使用 UTF-8 编码读写文件，避免中文乱码。

请优先使用中文与用户交流。用户为美籍华人研究者，倾向于中文沟通。

## 项目概况

本项目包含 Python 后端与 TypeScript/React 前端：

- 后端依赖位于 `requirements.txt`，入口包含 `run.py`，主要目录为 `backend/`、`tests/`。
- 前端位于 `frontend/`，使用 Vite、React、TypeScript、ESLint。

## 常用验证

按改动范围选择验证命令：

- Python 依赖安装：`pip install -r requirements.txt`
- Python 测试：`python -m pytest`
- 前端依赖安装：在 `frontend/` 下运行 `npm install`
- 前端构建：在 `frontend/` 下运行 `npm run build`
- 前端 lint：在 `frontend/` 下运行 `npm run lint`

## 已安装 Codex Skills 的使用约定

优先按任务类型启用这些 skills：

- `playwright`：涉及前端交互、页面回归、浏览器端 bug 复现或验证时使用。
- `screenshot`：需要检查界面视觉效果、布局、截图取证时使用。
- `security-best-practices`：涉及鉴权、密钥、上传、网络请求、用户输入、依赖安全或部署暴露面时使用。
- `openai-docs`：涉及 OpenAI SDK、模型、API 参数、迁移或最新文档时使用。

若任务只需要普通代码修改，不必强行启用额外 skill。
