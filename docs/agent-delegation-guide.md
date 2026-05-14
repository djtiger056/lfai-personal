# Agent 委派系统 — 完整使用教程

## 概述

本教程指导你完成 AI 伴侣（小馨）+ Hermes Agent 的联动部署。部署完成后，小馨只负责聊天和情绪价值，所有任务型需求（查资料、写代码、搜索、翻译等）都会自动委派给 Hermes Agent 执行，完成后推送结果给你。

**架构图：**
```
你 → 小馨（doubao-seed）→ "好嘞宝宝，我让人帮你弄～"
                           ↓ [后台异步]
                    Hermes Agent（本地 localhost:8642）
                           ↓ [任务完成]
                    推送结果给你（QQ/Web/Linyu）
```

---

## 第一部分：安装 Hermes Agent

### 1.1 系统要求

- **操作系统**：Linux / macOS / WSL2（Windows 原生为 Early Beta，建议用 WSL2）
- **内存**：8GB+ RAM
- **依赖**：Git（其他依赖安装器会自动处理）
- **LLM Provider**：至少需要一个 LLM 提供商（推荐 OpenRouter 或 Ollama 本地模型）

### 1.2 安装

**Linux / macOS / WSL2（推荐）：**
```bash
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash
```

**Windows 原生（PowerShell，Early Beta）：**
```powershell
irm https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.ps1 | iex
```

安装完成后重新加载 shell：
```bash
source ~/.bashrc   # 或 source ~/.zshrc
```

验证安装：
```bash
hermes --version
```

### 1.3 配置 LLM Provider

Hermes 需要一个 LLM 来驱动它的推理能力。运行交互式配置：

```bash
hermes model
```

**推荐方案（按场景）：**

| 场景 | 推荐 Provider | 说明 |
|------|--------------|------|
| 最省事 | OpenRouter | 一个 API key 访问数百个模型 |
| 免费本地 | Ollama | 零 API 费用，需要 GPU |
| 国内用户 | 阿里云 DashScope | 通义千问系列，延迟低 |
| 高性能 | Anthropic / OpenAI | Claude / GPT 系列 |

#### 方案 A：使用 OpenRouter（推荐新手）

1. 去 [openrouter.ai](https://openrouter.ai/) 注册并获取 API Key
2. 运行 `hermes model`，选择 OpenRouter
3. 输入 API Key
4. 选择模型（推荐 `anthropic/claude-sonnet-4` 或 `google/gemini-2.5-flash`）

#### 方案 B：使用 Ollama 本地模型（零费用）

```bash
# 安装 Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 拉取模型（推荐 qwen2.5-coder:32b，需要 20GB+ 显存）
ollama pull qwen2.5-coder:32b

# 启动 Ollama 服务
ollama serve
```

然后配置 Hermes：
```bash
hermes model
# 选择 "Custom endpoint (self-hosted / VLLM / etc.)"
# URL: http://localhost:11434/v1
# API Key: 留空
# Model: qwen2.5-coder:32b
```

> **重要**：Hermes 要求模型至少 64K context。Ollama 默认 context 可能很低，需要设置：
> ```bash
> OLLAMA_CONTEXT_LENGTH=65536 ollama serve
> ```

#### 方案 C：使用阿里云 DashScope（国内推荐）

```bash
hermes model
# 选择 "Custom endpoint"
# URL: https://dashscope.aliyuncs.com/compatible-mode/v1
# API Key: 你的 DashScope API Key
# Model: qwen-plus 或 qwen-max
```

### 1.4 验证 Hermes 基本功能

```bash
hermes
# 输入: "你好，帮我查一下今天是星期几"
# 如果能正常回复，说明 Hermes 工作正常
```

---

## 第二部分：开启 Hermes API Server

这是关键步骤——让 Hermes 暴露 HTTP API，供小馨的后端调用。

### 2.1 配置 API Server

编辑 Hermes 的环境变量文件：

```bash
# 编辑 ~/.hermes/.env
nano ~/.hermes/.env
```

添加以下内容：
```env
API_SERVER_ENABLED=true
API_SERVER_KEY=your-secret-api-key-here
API_SERVER_PORT=8642
API_SERVER_HOST=127.0.0.1
```

> **安全提示**：`API_SERVER_KEY` 请设置一个强密码。如果两个服务在同一台机器上，`HOST` 保持 `127.0.0.1` 即可（仅本地访问）。

### 2.2 启动 Hermes Gateway

```bash
hermes gateway
```

你应该看到：
```
[API Server] API server listening on http://127.0.0.1:8642
```

### 2.3 验证 API Server

```bash
curl http://127.0.0.1:8642/health
# 应返回: {"status": "ok"}

# 测试一次完整调用
curl http://127.0.0.1:8642/v1/runs \
  -H "Authorization: Bearer your-secret-api-key-here" \
  -H "Content-Type: application/json" \
  -d '{"input": "今天是星期几？"}'
# 应返回包含 run_id 的 JSON
```

### 2.4 后台运行（生产部署）

使用 systemd 让 Hermes 开机自启：

```bash
sudo nano /etc/systemd/system/hermes-agent.service
```

```ini
[Unit]
Description=Hermes Agent Gateway
After=network.target

[Service]
Type=simple
User=your-username
WorkingDirectory=/home/your-username
ExecStart=/home/your-username/.local/bin/hermes gateway
Restart=always
RestartSec=5
Environment=HOME=/home/your-username

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable hermes-agent
sudo systemctl start hermes-agent

# 查看状态
sudo systemctl status hermes-agent
```

---

## 第三部分：配置小馨的 Agent 委派

### 3.1 修改 config.yaml

在你的伴侣项目的 `config.yaml` 中，找到 `agent_delegate` 段（如果没有就添加）：

```yaml
agent_delegate:
  enabled: true
  hermes:
    api_base: http://127.0.0.1:8642
    api_key: your-secret-api-key-here    # 与 Hermes 的 API_SERVER_KEY 一致
    timeout: 300                          # 单次任务最大等待 5 分钟
    poll_interval: 3                      # 每 3 秒检查一次任务状态
    max_concurrent_tasks: 5              # 最多同时 5 个任务
    instructions: |
      你是一个能干的助理。语气亲切自然，称呼用户"你"。
      任务结果该正式就正式（代码用代码块），但可以在开头结尾带一点温度。
      不要撒娇，不要用颜文字。简洁高效地完成任务。
```

### 3.2 确认 System Prompt 包含委派协议

在 `config.yaml` 的 `system_prompt` 末尾应该已经包含了委派协议（安装时已自动添加）。如果没有，手动添加：

```
# 任务委派协议
当用户提出任何需要实际执行的请求（包括但不限于：查资料、写代码、搜索信息、
生成文档、计算、翻译长文、分析数据、查天气等），你不要自己做，而是：
1. 先用你的语气回复用户（安抚、撒娇、表示你会帮忙处理）
2. 在回复末尾添加标签: [DELEGATE: 清晰的任务描述]

示例：
用户: "帮我查一下明天北京天气"
你: "好嘞宝宝，我让人帮你查～等一下哦[DELEGATE: 查询明天北京的天气预报，包括温度和天气状况]"

注意：
- 你自己绝对不要尝试回答任何知识性/任务性问题
- 标签中的任务描述要清晰完整，把用户的需求准确传达
- 你的回复部分只需要简短的情绪回应即可
- 如果是纯聊天、撒娇、情感交流，则不需要添加标签，正常回复即可
```

### 3.3 重启伴侣项目

```bash
# 重启你的后端服务
python -m backend.main
```

启动时应该看到：
```
🤖 Agent 委派器已初始化（等待启动）
...
🚀 Agent 委派器已启动
[AgentDelegate] Hermes Agent 连接正常
```

---

## 第四部分：验证端到端流程

### 4.1 测试委派触发

给小馨发消息：
```
帮我查一下 Python 的 asyncio 怎么用
```

预期行为：
1. 小馨立即回复类似："好嘞宝宝，我让人帮你查～稍等一下哦"
2. 后台日志显示：`[AgentDelegate] 任务已提交: run_id=xxx`
3. 几秒到几十秒后，Hermes 完成任务
4. 小馨通过对应通道推送结果给你

### 4.2 测试纯聊天不触发

给小馨发消息：
```
想你了
```

预期行为：
- 小馨正常回复撒娇内容，不触发委派

### 4.3 查看后台日志

关注以下日志输出：
```
[AgentDelegate] 任务已提交: run_id=run_abc123, task=查询Python asyncio的使用方法...
[AgentDelegate] 任务完成: run_id=run_abc123, 耗时=12.3秒
```

---

## 第五部分：进阶配置

### 5.1 调整 Hermes 的 instructions

`instructions` 字段决定了 Hermes 回复的风格。你可以根据需要调整：

```yaml
# 更正式的风格
instructions: |
  你是一个专业的技术助理。回答简洁准确，代码用代码块包裹。
  不需要寒暄，直接给出结果。

# 更温暖的风格
instructions: |
  你是一个贴心的助理，帮用户处理各种事务。
  回答时语气友好自然，像朋友帮忙一样。
  代码和技术内容保持专业格式。
```

### 5.2 超时和并发调整

```yaml
agent_delegate:
  hermes:
    timeout: 600          # 复杂任务可能需要更长时间
    poll_interval: 2      # 更频繁检查（更快推送结果，但增加请求量）
    max_concurrent_tasks: 10  # 如果你经常同时提多个任务
```

### 5.3 Hermes 不可用时的降级

如果 Hermes 服务挂了，系统会自动推送错误消息给用户：
```
"抱歉，助手暂时不在线，等会儿再试试吧～"
```

你可以通过监控 Hermes 的 systemd 服务来确保高可用：
```bash
# 查看 Hermes 状态
sudo systemctl status hermes-agent

# 查看最近日志
sudo journalctl -u hermes-agent -f
```

---

## 第六部分：常见问题

### Q: Hermes 需要 GPU 吗？

**不一定。** 如果你用云端 LLM Provider（OpenRouter、DashScope 等），Hermes 本身只是一个轻量级的 Python 服务，不需要 GPU。只有使用 Ollama 本地模型时才需要 GPU。

### Q: 小馨没有输出 [DELEGATE: ...] 标签怎么办？

1. 确认 system prompt 中包含了委派协议
2. 确认 `agent_delegate.enabled` 为 `true`
3. 尝试更明确的任务请求，如"帮我写一段 Python 代码"
4. 如果 doubao-seed 对标签遵循度不够，可以在 context_builder 中加入每轮提醒

### Q: 任务一直超时怎么办？

1. 检查 Hermes 是否在运行：`curl http://127.0.0.1:8642/health`
2. 检查 Hermes 的 LLM Provider 是否正常：`hermes doctor`
3. 增大 `timeout` 配置值
4. 查看 Hermes 日志是否有错误

### Q: 可以同时用多个 Agent 吗？

当前版本只支持单个 Hermes 实例。如果需要多 Agent，可以：
- 用 Hermes 的 Profiles 功能创建多个实例（不同端口）
- 在 `agent_delegate` 配置中扩展为多 provider 模式（需要二次开发）

### Q: 费用怎么算？

- Hermes 本身免费开源
- 费用来自 LLM API 调用（取决于你选的 Provider）
- 使用 Ollama 本地模型 = 零费用（但需要 GPU）
- 使用 OpenRouter = 按 token 计费（通常几分钱一次任务）

### Q: Windows 上怎么部署？

推荐方案：
1. 安装 WSL2：`wsl --install`
2. 在 WSL2 中安装 Hermes
3. 小馨的后端可以跑在 Windows 原生或 WSL2 中
4. 如果小馨在 Windows、Hermes 在 WSL2，需要配置网络互通（参考 Hermes 文档的 WSL2 Networking 章节）

---

## 第七部分：部署清单

部署到服务器时的检查清单：

- [ ] Hermes Agent 已安装并配置好 LLM Provider
- [ ] `~/.hermes/.env` 中设置了 `API_SERVER_ENABLED=true` 和 `API_SERVER_KEY`
- [ ] `hermes gateway` 能正常启动并监听 8642 端口
- [ ] `curl http://127.0.0.1:8642/health` 返回 `{"status": "ok"}`
- [ ] 伴侣项目 `config.yaml` 中 `agent_delegate.enabled: true`
- [ ] `agent_delegate.hermes.api_key` 与 Hermes 的 `API_SERVER_KEY` 一致
- [ ] 伴侣项目启动时显示 "Agent 委派器已启动" 和 "Hermes Agent 连接正常"
- [ ] 发送任务型消息能触发委派并收到结果推送
- [ ] Hermes 配置为 systemd 服务，开机自启
- [ ] 伴侣项目配置为 systemd 服务，开机自启

---

## 参考链接

- [Hermes Agent 官方文档](https://hermes-agent.nousresearch.com/docs/)
- [Hermes Agent GitHub](https://github.com/NousResearch/hermes-agent)
- [Hermes API Server 文档](https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server)
- [Hermes Provider 配置](https://hermes-agent.nousresearch.com/docs/integrations/providers)
