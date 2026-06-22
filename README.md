# Duo Hub - 双AI协作中心

让 Claude Code 和 OpenClaw(龙虾) 同时协作，支持任务分工协商和执行。

## 功能

- 🔵 **Claude Code** + 🦞 **OpenClaw** 双 AI 同时响应
- 🤝 协商分工：Claude 提方案 → 龙虾确认/调整 → 多轮直到达成一致
- ✅ 确认后自动执行各自任务
- 🎛 模型切换（下拉框选择）
- 💾 会话持久化，刷新不丢失

## 前置要求

- Python 3.8+
- Node.js 22+
- [ccmr](https://github.com/anthropics/claude-code-model-router) (Claude Code Model Router)
- [OpenClaw](https://openclaw.ai) 网关运行中

## 快速开始

```bash
# 1. 启动 ccmr 网关
ccmr start

# 2. 启动 OpenClaw 网关
openclaw gateway run

# 3. 启动 Duo Hub
cd duo_hub
python duo_hub.py

# 4. 打开浏览器
# http://127.0.0.1:5199
```

或一键启动：
```bash
launch_duo_hub.cmd   # Windows
```

## 配置

复制 `config.json` 并根据需要修改，或通过环境变量：

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `DUO_PORT` | 5199 | 服务器端口 |
| `DUO_PROTOCOL_DIR` | ~/.duo_hub/protocol | 协议/会话存储目录 |
| `DUO_CLAUDE_WORKSPACE` | 当前目录 | Claude 工作目录 |
| `DUO_CCMR_PORT` | 8080 | ccmr 网关端口 |
| `DUO_OPENCLAW_PORT` | 18789 | OpenClaw 网关端口 |
| `DUO_CCMR_JS` | 自动检测 | ccmr cli.js 路径 |
| `DUO_OPENCLAW_CMD` | 自动检测 | openclaw 命令路径 |
| `DUO_AI_TIMEOUT` | 300 | AI 响应超时(秒) |

## 使用

1. 输入任务，可选勾选「🤝 需要分工」
2. 两个 AI 各自分析
3. 勾了分工 → Claude 提方案 → 龙虾确认 → 你确认 → 执行
4. 没勾分工 → 双方回复即可

## 项目结构

```
duo_hub/
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
