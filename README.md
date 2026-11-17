# Duo Hub

Duo Hub 是一个本机 Agent 协作看板。当前 `0.6.2` 阶段由 Codex 负责主管调度，只启用一个逻辑席位 `gemini`；默认通过已登录的 Antigravity CLI 调用 Gemini 模型。

Claude Code 和 OpenClaw 的旧实现仍保留为兼容代码，但没有注册到当前 Agent Registry，也不会出现在页面或默认调用链中。

## 当前能力

- 注册表驱动：后端、API 和页面从同一个 Agent Registry 读取参与方，不再把面板写死为固定三方。
- 可替换 provider：逻辑席位仍叫 `gemini`，实际调用来源单独记录为 `antigravity-cli` 或 `gemini-cli`。
- 真实 CLI 回包：默认用 Antigravity CLI 的 headless JSON 模式调用 `gemini-4-hydrogen-medium`。
- 明确调用护栏：普通发送只记录内容；只有勾选“启用 Agent 调用”才会实际消耗模型额度。
- 只读分析模式：Phase 1 的 Gemini 调用固定为 plan/分析模式，不允许模型直接改文件、发布或执行账号动作。
- 可审计事件：`events.jsonl` 逐条保存可见 prompt/output 事件、actor、recorded_by、provider、model、退出码、耗时、usage 和内容哈希。
- 会话恢复：`session.json`、`chat.json`、outbox 和事件序号在服务重启后继续恢复。
- 动态页面：Agent 面板、模型列表、网关状态、分工状态和聊天角色均按 API 返回的注册表生成。
- 本机请求保护：所有 POST 必须携带 HttpOnly 同源 cookie 或 `X-Duo-Hub-Token`，拒绝非回环 Host、恶意 Origin 和宽泛 CORS。
- 可取消运行：重置会话会终止当前 provider 进程树；旧 run ID 与 session ID 失效后不能写入新会话或新 outbox。

## 架构

```text
浏览器 / 后续桌面壳
        |
        v
Duo Hub HTTP API
        |
        +-- Agent Registry -- logical id: gemini
        |                         |
        |                         +-- provider: antigravity-cli (默认)
        |                         +-- provider: gemini-cli (可选)
        |
        +-- session.json / chat.json / outbox
        +-- events.jsonl (append-only 可见事件)
```

`actor` 表示是谁产生内容，`recorded_by` 表示谁写入事件，`provider` 表示实际调用通道；三者不会混写。例如当前成功回包应记录为：

```json
{
  "actor": "gemini",
  "recorded_by": "duo-hub",
  "provider": "antigravity-cli",
  "model": "gemini-4-hydrogen-medium"
}
```

## 依赖

- Python 3.10+
- 默认路径：Antigravity CLI 已安装并完成登录
- 可选路径：Google Gemini CLI 已安装，并已通过 Google 登录、`GEMINI_API_KEY` 或 Vertex AI 完成认证

当前默认配置不要求 ccmr、Claude Code 或 OpenClaw 网关运行。

## 启动

PowerShell：

```powershell
Set-Location C:\Users\tianhuo\Documents\GitHub\duo-hub
python .\duo_hub.py
```

然后打开 <http://127.0.0.1:5199/>。

用于隔离验证时，可以指定独立协议目录并禁止自动打开浏览器：

```powershell
$env:DUO_PROTOCOL_DIR = "$env:TEMP\duohub-test\protocol"
$env:DUO_GEMINI_WORKSPACE = (Get-Location).Path
$env:DUO_NO_BROWSER = "1"
python .\duo_hub.py
```

## 配置 Agent provider

默认 `config.json`：

```json
{
  "agents": [
    {
      "id": "gemini",
      "enabled": true,
      "invoke_by_default": true,
      "provider": "antigravity-cli",
      "model": "gemini-4-hydrogen-medium"
    }
  ]
}
```

若 Gemini CLI 已完成认证，可把 provider 切换为 `gemini-cli`，并选择其支持的模型。Duo Hub 会在回包 metadata 中保留真实 provider，不能把 Antigravity CLI 的结果冒充为 Gemini CLI 结果。

常用环境变量：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DUO_PORT` | `5199` | 本机 HTTP 端口 |
| `DUO_PROTOCOL_DIR` | `%USERPROFILE%\.duo_hub\protocol` | 会话、聊天、outbox 与事件目录 |
| `DUO_GEMINI_WORKSPACE` | 跟随 Codex 工作区 | Gemini 席位的工作目录 |
| `DUO_ANTIGRAVITY_CMD` | 自动检测 | `agy.exe` 的完整路径 |
| `DUO_GEMINI_CMD` | 自动检测 | `gemini.cmd` 的完整路径 |
| `DUO_API_TOKEN` | 自动生成 | 覆盖本机 POST API token；默认保存在协议目录的 `api_token` |
| `DUO_NO_BROWSER` | 空 | 设为 `1` 时不自动打开浏览器 |

## API

- `GET /api/state`：会话、动态 Agent 列表、provider 健康状态、分工与最近消息。
- `POST /api/task`：记录任务；`allow_paid_agents=true` 时才实际调用当前 Agent。
- `POST /api/supervisor/delegate`：Codex 主管委派给一个已注册 Agent。
- `POST /api/supervisor/assign`：按注册表下发一组任务。
- `POST /api/set-model`：切换逻辑席位模型。
- `POST /api/loop-scan`：不调用模型，只检查本地状态并写 Loop 报告。
- `POST /api/stop`：归档当前会话并创建新会话。

最小调用示例：

```powershell
$body = @{
  text = "请分析这个方案，只返回结论和风险"
  needs_division = $false
  allow_paid_agents = $true
} | ConvertTo-Json
$token = (Get-Content "$env:USERPROFILE\.duo_hub\protocol\api_token" -Raw).Trim()

Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:5199/api/task `
  -Headers @{ "X-Duo-Hub-Token" = $token } `
  -ContentType "application/json; charset=utf-8" `
  -Body $body
```

## 验证

```powershell
python -m compileall -q .\duo_hub.py .\duohub
python -m unittest discover -s tests -v
node --check .\web\app.js
node --check .\web\supervisor_status.js
```

Phase 1 已完成 Gemini Registry、真实回包、metadata 审计和重启恢复。Phase 2 已完成 POST token、同源/回环限制、安全响应头、provider 进程树取消和旧会话写入隔离。Phase 3 的本机实测结论是：Antigravity CLI 当前已认证、可结构化回包且可审计，继续作为默认 provider；Gemini CLI 保留为用户完成认证后的备用入口。详细对比见 `docs/DUO_HUB_GEMINI_ANTIGRAVITY_COMPARISON_2026-11-17.md`。
