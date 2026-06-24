# Duo Hub - 三AI协作中心

当前版本：`0.4.6`

让 Claude Code、OpenClaw(龙虾) 和 Codex 同时协作，支持任务分工协商和执行。

## 功能

- 🔵 **Claude Code** + 🦞 **OpenClaw** + 🟢 **Codex** 三 AI 同时响应
- 🤝 协商分工：Codex 汇总三方意见 → Claude/龙虾确认或调整 → 不一致时暂停等待用户裁决
- 🧭 用户裁决：确认执行、输入修改意见、继续协商、取消分工
- ✅ 确认后自动执行各自任务
- 🎛 模型切换（下拉框选择）
- 🌌 JARVIS 语义控制台：小窗/缩小时是恒星态自转，放大后才展开为带节点文字和状态读数的全息信息态
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
ccmr start

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
| `DUO_CCMR_PORT` | 8080 | ccmr 网关端口 |
| `DUO_OPENCLAW_PORT` | 18789 | OpenClaw 网关端口 |
| `DUO_CCMR_JS` | 自动检测 | ccmr cli.js 路径 |
| `DUO_OPENCLAW_CMD` | 自动检测 | openclaw 命令路径 |
| `DUO_CODEX_CMD` | 自动检测 | codex 命令路径，Windows 优先 codex.cmd |
| `DUO_AI_TIMEOUT` | 300 | AI 响应超时(秒) |

## 使用

1. 输入任务，可选勾选「🤝 需要分工」
2. 三个 AI 各自分析
3. 勾了分工 → Codex 汇总提案 → Claude/龙虾确认
4. 如果三方一致 → 你确认 → 三方执行
5. 如果有分歧 → 面板暂停，允许你输入修改意见、继续协商、强制确认当前方案或取消分工
6. 没勾分工 → 三方回复即可

## 设计修正

旧版把参与者写死成 `claude/lobster` 两方，协商流程固定为「Claude 提方案 → 龙虾确认」。这会导致：

- 新参与者无法自然接入
- 一方说“同意但需要调整”也可能被关键词误判为协商完成
- 状态机存在 `awaiting_user` 等前端未覆盖状态

新版改为三方流程：初始阶段三方并行响应；需要分工时由 Codex 汇总三方意见提出结构化分工，Claude 和龙虾并行确认；只有明确一致时才进入普通确认。若任何一方不同意或要求补充确认，面板进入用户裁决状态，不再把分歧伪装成最终结果。

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
