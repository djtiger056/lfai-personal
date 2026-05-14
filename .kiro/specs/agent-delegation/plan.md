# Agent 委派系统 — 实现计划书

## 概述

让 AI 伴侣（小馨）能够将任务型需求委派给本地 Hermes Agent 执行。小馨只负责聊天和情绪价值，所有"干活"的事（查资料、写代码、生成文档等）都交给 Hermes。

## 核心架构

```
用户消息 → 小馨 LLM → 回复中包含 [DELEGATE: 任务描述] 标签
                         │
                         ├─ 立即回复（去掉标签后的文本，如"好嘞宝宝，我让人帮你弄～"）
                         │
                         └─ 后台异步：AgentDelegator
                              │
                              ▼
                         POST /v1/runs → Hermes Agent (localhost:8642)
                              │
                              ▼ (轮询状态直到完成)
                         拿到结果
                              │
                              ▼
                         通过 ProactiveChatScheduler 推送给用户
```

## 设计决策

| 决策点 | 选择 | 原因 |
|--------|------|------|
| 触发方式 | LLM 自主判断，输出 `[DELEGATE: ...]` 标签 | 类似现有 `[GEN_IMG: ...]` 模式，无需改 provider |
| 调用方式 | HTTP API (Hermes Runs API) | 天然异步，支持状态轮询和取消 |
| 结果推送 | 复用 ProactiveChatScheduler 的 sender 通道 | 不造轮子，QQ/Web/Linyu 全通道覆盖 |
| 人格适配 | 给 Hermes 传 instructions（轻量人格） | 让输出风格亲切但不撒娇 |
| 错误处理 | 直接返回完整错误信息 | 用户明确要求 |
| 部署 | 同一台服务器 localhost:8642 | 用户确认 |

## 文件结构

```
backend/
├── agent_delegate/
│   ├── __init__.py
│   ├── config.py          # 配置模型（Hermes 地址、API key、超时等）
│   ├── client.py          # Hermes HTTP 客户端（Runs API 封装）
│   ├── delegator.py       # 核心调度器（解析标签、提交任务、轮询、推送结果）
│   └── parser.py          # [DELEGATE: ...] 标签解析器
```

## 详细实现计划

### Phase 1: 基础设施

#### 1.1 配置 (`backend/agent_delegate/config.py`)

在 `config.yaml` 中新增配置段：

```yaml
agent_delegate:
  enabled: true
  hermes:
    api_base: http://127.0.0.1:8642
    api_key: "your-hermes-api-key"
    timeout: 300              # 单次任务最大等待秒数
    poll_interval: 3          # 轮询间隔秒数
    instructions: |
      你是一个能干的助理。语气亲切自然，称呼用户"你"。
      任务结果该正式就正式（代码用代码块），但可以在开头结尾带一点温度。
      不要撒娇，不要用颜文字。
```

#### 1.2 Hermes HTTP 客户端 (`backend/agent_delegate/client.py`)

封装 Hermes Runs API：
- `submit_run(task: str, instructions: str) -> str`  — 提交任务，返回 run_id
- `poll_run(run_id: str) -> RunStatus`  — 查询状态
- `get_run_result(run_id: str) -> str`  — 获取完成后的输出
- `stop_run(run_id: str)`  — 取消任务

使用 `aiohttp` 异步 HTTP（与项目现有依赖一致）。

#### 1.3 标签解析器 (`backend/agent_delegate/parser.py`)

- 从 LLM 回复中提取 `[DELEGATE: 任务描述]` 标签
- 返回 `(cleaned_text, task_description)` 元组
- 支持标签在回复中任意位置
- 如果没有标签，返回 `(original_text, None)`

### Phase 2: 核心调度

#### 2.1 委派调度器 (`backend/agent_delegate/delegator.py`)

```python
class AgentDelegator:
    """管理任务委派的生命周期"""
    
    async def start()          # 启动后台 worker
    async def stop()           # 停止
    async def submit(task, user_id, session_id, channel)  # 提交任务
    async def _worker()        # 后台循环：轮询进行中的任务
    async def _on_complete(task_record)   # 任务完成回调 → 推送结果
    async def _on_failed(task_record)     # 任务失败回调 → 推送错误
```

内部维护一个任务队列（内存 dict，key=run_id），后台 worker 定期轮询所有进行中的任务状态。

#### 2.2 与 Bot 集成

在 `Bot.__init__` 中初始化 `AgentDelegator`（如果 enabled）。

在 `Bot.chat()` 和 `Bot.chat_stream()` 的回复后处理中：
1. 调用 `parser.extract_delegate_tag(response)` 
2. 如果有标签 → 提交任务到 delegator，返回 cleaned_text
3. 如果没有 → 正常返回

类似现有的 `_process_image_in_response()` 模式。

### Phase 3: 结果推送

#### 3.1 推送通道

复用 `ProactiveChatScheduler` 的 `sender` 回调：
- delegator 完成任务后，调用 scheduler 的 sender 将结果推送给对应 channel 的用户
- 需要在 delegator 中持有 scheduler 的引用

推送格式：直接发送 Hermes 的输出文本（已经过轻量人格适配）。

### Phase 4: System Prompt 修改

在小馨的 system prompt 中新增委派协议段：

```
# 任务委派协议
当用户提出任何需要实际执行的请求（包括但不限于：查资料、写代码、搜索信息、
生成文档、计算、翻译长文、分析数据等），你不要自己做，而是：
1. 先用你的语气回复用户（安抚、撒娇、表示你会帮忙处理）
2. 在回复末尾添加标签: [DELEGATE: 清晰的任务描述]

示例：
用户: "帮我查一下明天北京天气"
你: "好嘞宝宝，我让人帮你查～等一下哦[DELEGATE: 查询明天北京的天气预报，包括温度和天气状况]"

用户: "帮我写个Python排序算法"
你: "没问题！我找人帮你写，稍等一下下～[DELEGATE: 用Python写一个高效的排序算法，包含冒泡排序和快速排序的实现，附带注释]"

注意：
- 你自己绝对不要尝试回答任何知识性/任务性问题
- 标签中的任务描述要清晰完整，把用户的需求准确传达
- 你的回复部分只需要简短的情绪回应即可
```

## 实现顺序

1. **Phase 1** — config + client + parser（纯基础设施，可独立测试）
2. **Phase 2** — delegator + bot 集成（核心逻辑）
3. **Phase 3** — 推送通道对接（端到端打通）
4. **Phase 4** — system prompt 修改（最后开启）

## 配置示例 (config.yaml 新增段)

```yaml
agent_delegate:
  enabled: true
  hermes:
    api_base: http://127.0.0.1:8642
    api_key: "change-me-local-dev"
    timeout: 300
    poll_interval: 3
    max_concurrent_tasks: 5
    instructions: |
      你是一个能干的助理。语气亲切自然，称呼用户"你"。
      任务结果该正式就正式（代码用代码块），但可以在开头结尾带一点温度。
      不要撒娇，不要用颜文字。简洁高效地完成任务。
```

## 依赖

- 无新增外部依赖（使用现有的 `aiohttp`）
- Hermes Agent 需要在同一台服务器上运行并开启 API Server

## 风险与注意事项

1. **Hermes 不可用时的降级**：如果 Hermes 连接失败，delegator 应该推送一条错误消息告知用户"助手暂时不在线"
2. **任务超时**：超过 timeout 秒未完成的任务自动标记失败并通知用户
3. **并发控制**：限制同时进行的任务数（max_concurrent_tasks），超出时排队
4. **标签误触发**：LLM 可能在不该委派时输出标签，但由于 system prompt 明确指示"所有任务都委派"，这个问题不大
5. **doubao-seed 对标签的遵循度**：需要实际测试，如果遵循度不够好，可以考虑在 context_builder 中每次注入提醒
