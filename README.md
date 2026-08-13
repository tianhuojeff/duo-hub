# Duo Hub - 三AI协作中心

当前版本：`0.5.16`

让 Codex 作为主管直接派发 Claude Code、OpenClaw(龙虾) 和 Codex 三方分工，Duo Hub 负责展示派发、回包和协作状态。

## 功能

- 🧭 **Codex 主管模式**：主对话留在 Codex，Codex 负责拆任务、派发、汇总和裁决，Duo Hub 展示透明调度过程
- 🧩 Supervisor API：`/api/supervisor/note` 记录 Codex 裁决，`/api/supervisor/delegate` 委派给单个参与方，`/api/supervisor/assign` 一次性下发三方分工
- 🔵🦞🟢 保留三 AI 广播/协商入口，用于手动测试或需要平级协商的任务
- 🤝 协商分工：Codex 汇总三方意见 → Claude/龙虾确认或调整 → 不一致时暂停等待用户裁决
- 🧭 用户裁决：确认执行、输入修改意见、继续协商、取消分工
- ✅ 确认后自动执行各自任务
- 🎛 模型切换（下拉框选择）
- 💰 付费 Agent 护栏：默认发送只记录任务，不启动三方模型；勾选后才调用 Claude、龙虾和 Codex
- ⚡ 工作中快速刷新：三方执行/协商时前端更快收集已完成回复，空闲时自动降频
- 🚀 轻量回复路径：普通阅读/回复时，模型槽位可直连本地 ccmr 网关
- 🛟 模型来源审计：界面保留槽位与底层模型的映射，不把代理模型冒充为其他模型
- 🧯 协议文件容错：`chat.json` 被手动写成数组时会自动合并回 `messages` 结构，避免状态接口被坏结构拖死
- 🧊 静默 HTTP 访问日志：默认不打印高频轮询日志，避免 Windows 后台重定向阻塞前端响应
- 💤 后台启动静默：`DUO_NO_BROWSER=1` 或 `DUO_QUIET=1` 时跳过启动横幅输出，避免卡在已监听但未进入服务循环的半启动状态
- 🔒 开代理时自动为 `127.0.0.1/localhost/::1` 设置本地直连，外网流量仍按用户代理设置走
- 🩺 心跳/连接检查不会调用模型：`说话`、`来`、`检查连接` 等短任务直接返回本地网关状态
- 🔁 Loop 扫描：不调用模型，只检查本地网关、会话、分工阻塞、outbox 和仓库变更，并写入 `loop_state.json` / `loop_report.md`
- 🌌 JARVIS 语义控制台：语义星体分布在三维球面，滚轮/手势缩放内容，鼠标轨迹球拖动支持任意方向旋转惯性
- 💾 会话持久化，刷新不丢失

## 前置要求

- Python 3.8+
- Node.js 22+
- [ccmr](https://github.com/anthropics/claude-code-model-router) (Claude Code Model Router)
- [OpenClaw](https://openclaw.ai) 网关运行中
- Codex CLI 已登录并可运行

## 快速开始

```bash
# 1. 启动 ccmr 网关
ccmr start --port 18080 --host 127.0.0.1

# 2. 启动 OpenClaw 网关
openclaw gateway run

# 3. 启动 Duo Hub
cd duo-hub
python duo_hub.py

# 4. 打开浏览器
# http://127.0.0.1:5199
```

或一键启动：
```bash
launch_duo_hub.cmd   # Windows
```

## 配置

默认读取 `config.json`。本机私有路径建议写到已被 `.gitignore` 忽略的 `config.local.json`，会覆盖 `config.json`；也可以通过环境变量覆盖：

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `DUO_PORT` | 5199 | 服务器端口 |
| `DUO_PROTOCOL_DIR` | ~/.duo_hub/protocol | 协议/会话存储目录 |
| `DUO_CLAUDE_WORKSPACE` | 当前目录 | Claude 工作目录 |
| `DUO_CODEX_WORKSPACE` | 当前目录 | Codex 工作目录 |
| `DUO_CCMR_PORT` | 18080 | ccmr 网关端口 |
| `DUO_OPENCLAW_PORT` | 18789 | OpenClaw 网关端口 |
| `DUO_CCMR_JS` | 自动检测 | ccmr cli.js 路径 |
| `DUO_OPENCLAW_CMD` | 自动检测 | openclaw 命令路径 |
| `DUO_CODEX_CMD` | 自动检测 | codex 命令路径，Windows 优先 codex.cmd |
| `DUO_AI_TIMEOUT` | 300 | AI 响应超时(秒) |

## 使用

默认推荐把 Codex 当前对话作为主控入口，Duo Hub 只做调度看板：

1. 用户在 Codex 对话里提出任务。
2. Codex 判断是否需要三方分工；不需要时直接解决。
3. 需要三方分工时，Codex 调用 `/api/supervisor/assign`，分别给 `claude`、`lobster`、`codex` 下发不同任务。
4. Duo Hub 页面展示三方分工内容、各自状态、回包和完成状态。
5. Codex 在当前对话里汇总、裁决、执行后续动作，并用 `/api/supervisor/note` 把关键裁决同步到看板。

仍保留旧手动入口：

1. 在 Duo Hub 输入任务，可选勾选「🤝 需要分工」。
2. 默认发送只记录任务，不调用付费 Agent；需要三方实际分析时勾选「💰 启用三方调用」并确认。
3. 勾了分工时仍可走旧的三方广播/协商流程。

Supervisor API 示例：

```bash
curl -s -H "Content-Type: application/json" \
  -d "{\"role\":\"codex\",\"content\":\"Codex 主管：这里是主对话，Duo Hub 是透明看板。\"}" \
  http://127.0.0.1:5199/api/supervisor/note

curl -s -H "Content-Type: application/json" \
  -d "{\"target\":\"claude\",\"text\":\"请检查这个实现方向是否有明显风险。\"}" \
  http://127.0.0.1:5199/api/supervisor/delegate

curl -s -H "Content-Type: application/json" \
  -d "{\"assignments\":{\"claude\":\"审查方案风险和遗漏。\",\"lobster\":\"验证本机 OpenClaw/任务状态。\",\"codex\":\"实现代码改动并汇总结果。\"}}" \
  http://127.0.0.1:5199/api/supervisor/assign
```
8. 点「Loop 扫描」可做一次本地闭环检查；它只读本地状态，不调用 Claude、龙虾或 Codex

## 设计修正

旧版把参与者写死成 `claude/lobster` 两方，协商流程固定为「Claude 提方案 → 龙虾确认」。这会导致：

- 新参与者无法自然接入
- 一方说“同意但需要调整”也可能被关键词误判为协商完成
- 状态机存在 `awaiting_user` 等前端未覆盖状态

新版改为三方流程：初始阶段三方并行响应；需要分工时由 Codex 汇总三方意见提出结构化分工，Claude 和龙虾并行确认；只有明确一致时才进入普通确认。若任何一方不同意或要求补充确认，面板进入用户裁决状态，不再把分歧伪装成最终结果。

## Loop 扫描

`Loop 扫描` 是 Duo Hub 的最小工程闭环，不负责自动启动三方模型。它做四件事：

- 发现：读取当前 phase、三方状态、网关在线状态、outbox 更新时间和仓库变更。
- 判断：识别等待用户确认、协商分歧、网关离线、Agent 超时/错误等阻塞项。
- 记录：写入协议目录下的 `loop_state.json` 和 `loop_report.md`。
- 交接：在前端显示当前 Loop 状态和第一条下一步动作。

这个功能对应 Loop Engineering 的“状态文件 + 验证者 + 下一步”部分；真正调用付费 Agent 仍必须由用户勾选「启用三方调用」。

## 版本规则

每次更新并推送 GitHub 前，必须同步更新：

- `VERSION`
- `duo_hub.py` 里的 `APP_VERSION`
- README 顶部的当前版本

## 项目结构

```
duo-hub/
├── duo_hub.py          # 主服务器
├── config.json         # 配置文件
├── launch_duo_hub.cmd  # Windows 一键启动
├── web/
│   ├── index.html
│   ├── style.css
│   └── app.js
├── README.md
└── .gitignore
```
