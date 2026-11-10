---
title: Duo Hub｜Notion 协作、Gemini 接入与桌面应用化完整研究路线
date: 2026-11-10
timezone: Asia/Shanghai
status: research-approved-for-human-review
written_by: codex
source_agent: codex
coordinator: 天火
repository: tianhuojeff/duo-hub
baseline_version: 0.5.16
notion_changed_in_this_round: false
---

# Duo Hub｜Notion 协作、Gemini 接入与桌面应用化完整研究路线

> 来源：`codex`
> 署名：Codex
> 编写时间：2026-11-10 18:33（Asia/Shanghai）
> 当前性质：研究、架构决策与跨 Agent 交接基线，不是已实施功能说明。
> 本轮边界：只把研究路线和当日工作日志写入 Duo Hub Git 仓库；**没有修改 Notion、Notion 规则、Duo Hub 代码、运行配置、服务或进程。**

## 0. 文档目的

本文件把 2026-11-10 围绕 Duo Hub 的全部研究、用户纠正、当前证据、目标架构、Notion 框架、Gemini 接入、桌面应用化路线、Codex/Claude 分工、迁移风险与验收门槛统一成一份正式交接材料。

在 Duo Hub 端到端跑通以前：

- 天火是 Codex 与 Claude 之间的协调者和最终决策者；
- Codex 与 Claude 不得并行改写同一份文件、同一分支工作树或同一个 Notion 结构；
- 每一位 Agent 接手前都应先读本文件、当前仓库状态、用户最新指令和适用规则；
- 本文件可以指导后续实施，但不能替代用户对外部写入、Notion 修改、发布、删除、账号和凭证操作的明确授权；
- 后续 Claude 应在天火明确要求后读取本文件，再从真实仓库状态继续 Codex 的工作，不能仅依据聊天摘要猜测。

## 1. 用户要求与最新纠正

### 1.1 第一轮要求的完整含义

用户要求继续研究 Duo Hub，并以 Notion 中的最新版规则为基线，重新定义 Duo Hub 的工作区和多 Agent 协作方式：

1. Duo Hub 服务中的 Agent 按 Notion 最新版 `agent规则` 工作；
2. Notion 成为简易版 Duo Hub 协作工作区；
3. Duo Hub 内的任务分工、各 Agent 会话记录和工作日志完整保存到 Notion；
4. 当前主要协作对象是 Codex 与 Claude；
5. 下一软件版本重点加入 Gemini；
6. Gemini 直接接入 Notion 困难时，由调用 Gemini 的 Codex 或 Claude 代为写入 Gemini 的任务、输入、输出和日志；
7. 在 Notion 根目录建立正式框架；
8. 后续规则更新必须遵守现有版本迭代规则，并明确写明由 `codex` 更新；
9. Codex 与 Claude 共同完成，但先提交研究路线给用户审核，审核前不实施；
10. 后续希望 Duo Hub 成为真正的应用，以提升稳定性。

### 1.2 用户对“共同规则”的纠正

Codex 最初错误地把 Notion v9 中“所有 Agent 共用规则”和“多 Agent 共同规则（Claude Code 工作区）”理解成与新方向冲突。

用户随后明确纠正：

- **没有冲突；Duo Hub 就是使用 Notion 这里的最新版共同规则；**
- 不再采用的是原先另外设置的“共同工作区/共同规则载体”；
- 不能因此删除 Notion 的共同规则，不能把所有 Agent 共用规则拆成多份互相漂移的副本。

因此正式口径是：

> Notion 根目录 `agent规则` 的最新生效版本继续作为 Duo Hub 的共同规则真源；旧的独立共同工作区、共享规则副本和记忆桥退出，不再作为规则或协作记录真源。

### 1.3 用户对 `SHARED_MEMORY.md` 的最终纠正

用户进一步明确：

- 不需要再设计、修复或迁移 `SHARED_MEMORY.md`；
- 所谓记忆桥已经被后续要建立的 Notion 根目录 Duo Hub 协作框架取代；
- 对话日志和工作日志直接进入新的 Notion Duo Hub 工作区；
- 后续 Claude 规则更新时，应删除旧记忆桥逻辑，而不是把它改名或描述成另一座记忆桥。

因此：

- `SHARED_MEMORY.md` 不属于新架构；
- `AISharedMemory\duo_hub_protocol` 也不能继续承担“共享记忆/共同工作区”职责；
- 若软件为了断网恢复保留本地 SQLite 或待同步队列，它只能是应用内部技术缓存，不能称为共同工作区、记忆桥或规则来源。

### 1.4 用户对“应用化时点”的纠正

用户明确 Duo Hub 的目标一直是应用，而不是长期停留在网页：

- 如果继续开发 HTML 会与最终应用完全不同，应立即进入应用开发；
- 如果当前 HTML 只是差一个应用包装，允许继续开发，最后再封装；
- 这一轮仍不修改任何内容，只做判断。

只读检查后的结论是：

> 现有 HTML/CSS/JavaScript 大部分可以直接作为桌面应用的渲染层，不需要推倒重写；但从下一实施轮起必须按桌面应用架构重构通信、生命周期、Agent 注册和资源加载，不能继续把它当普通网页无边界扩张。安装包可以在 Notion/Gemini 主链稳定后制作。

### 1.5 当前协调关系

用户最新指定：

- 在项目完整跑通以前，天火作为 Codex 与 Claude 的协调者；
- 当前由 Codex写下完整研究路线；
- 后续天火会让 Claude 读取本文件并继续 Codex 的工作；
- Claude 接手时必须以本文件和实时仓库为准；
- 本轮不修改 Notion。

## 2. 当前事实基线

### 2.1 仓库与版本

- 正式仓库：`C:\Users\tianhuo\Documents\GitHub\duo-hub`
- Git 远程：`https://github.com/tianhuojeff/duo-hub.git`
- 当前分支：`master`
- 研究时工作树：干净，`master...origin/master`
- 当前 HEAD：`30ad8c74243a3cffcf8dcaa869d500e978d3685d`
- 当前应用版本：`0.5.16`
- 当前 README 定义：Codex 主管，Claude Code、OpenClaw/龙虾、Codex 三方协作。

### 2.2 当前代码规模与结构

研究时主要文件：

| 文件 | 大小/性质 | 现状 |
|---|---:|---|
| `duo_hub.py` | 约 89 KB | Python 单文件服务器、Agent 调用、状态机、协议存储、HTTP API 混合在一起 |
| `web/app.js` | 约 85 KB | 页面状态、API 调用、消息渲染、星图、动画、手势识别混合在一起 |
| `web/index.html` | 约 8 KB | 写死 Claude、龙虾、Codex 三个面板和模型下拉框 |
| `web/style.css` | 约 21 KB | 主界面样式 |
| `web/supervisor_status.js` | 约 5 KB | 三方主管状态面板 |
| `launch_duo_hub_app.ps1` | 约 9.6 KB | Python/网关检测、端口控制、后台服务、Chrome `--app` 启动 |
| `launch_duo_hub.cmd` | 约 2.7 KB | 旧式一键启动路径 |

### 2.3 当前 Agent 模型是硬编码的

`duo_hub.py` 当前含有：

- `AI_ORDER = ("claude", "lobster", "codex")`；
- `SUPERVISOR_TARGETS = AI_ORDER`；
- `OUTBOX_CLAUDE`、`OUTBOX_LOBSTER`、`OUTBOX_CODEX`；
- `run_claude`、`run_lobster`、`run_codex` 一类角色特定执行路径；
- 前端 HTML、状态徽章和模型选择同样分别写死三方。

这意味着：

- Gemini 不能通过简单配置自然加入；
- 移除或停用 OpenClaw 会涉及前后端多处修改；
- 当前“三方”文案、状态机和 UI 与用户最新的“Codex＋Claude 为主，下一版本加入 Gemini”不一致；
- 后续必须先建立 Agent Registry 和统一 Adapter，再加入 Gemini。

### 2.4 当前会话与协议存储

当前代码使用：

- `session.json`：会话阶段、轮次、Agent 状态、模型和当前任务；
- `chat.json`：消息集合；
- `inbox/current_task.txt`：共享任务文本；
- `outbox/claude.md`、`outbox/lobster.md`、`outbox/codex.md`：各 Agent 回包；
- `loop_state.json`、`loop_report.md`：Loop 扫描结果。

研究时 `C:\Users\tianhuo\AISharedMemory\duo_hub_protocol` 仅有空消息 `chat.json` 和 idle `session.json`，最近状态来自 2026-09-11 凌晨；没有正式规则、完整项目日志或 Notion 同步证据。

当前问题：

- 本地 JSON 是可覆盖状态，不是严格追加的审计事件流；
- 缺少稳定 event ID、序号、内容哈希和幂等写入；
- 缺少“执行状态”和“Notion 归档状态”的区分；
- 没有崩溃后保证完整补写的事务性 outbox；
- 没有 Notion 数据库、页面或 API 接口；
- 没有 Gemini 角色、调用器和日志代理；
- API 状态页面只返回最近消息，不是完整持久审计面。

### 2.5 当前“应用”仍是浏览器应用模式

`launch_duo_hub_app.ps1` 最终使用 Chrome：

`Start-Process -FilePath $Chrome -ArgumentList @(..., "--app=$Url")`

因此它目前是：

- Python 本地 HTTP 服务；
- Chrome 无地址栏应用模式窗口；
- 多个外部网关/CLI 进程；
- 启动脚本负责端口和进程生命周期；
- 不是独立安装、单实例、统一崩溃恢复的桌面应用。

这并不意味着前端必须重写。现有 HTML/CSS/JS 使用标准 DOM、Canvas、Fetch 和 Pointer Events，适合继续作为 WebView2/pywebview 或 Tauri WebView 的渲染层。

### 2.6 当前前端需要提前处理的应用兼容问题

可以直接复用：

- HTML 布局；
- CSS 视觉设计；
- Canvas 星图；
- 鼠标、滚轮、触控/指针交互；
- 消息与状态渲染；
- 主管看板；
- 相对简单的 `fetch("/api/...")` 通信模式。

必须在打包前处理：

1. `app.js` 过大，页面业务、动画、状态机和手势耦合；
2. `index.html` 用根路径 `/style.css`、`/app.js`，需要适配应用资源路径；
3. Agent 面板与模型选择写死；
4. `location.reload()` 需要改为应用生命周期可控的重置；
5. 高频轮询需要统一取消、超时和窗口休眠策略；
6. MediaPipe 通过 jsDelivr 动态 import；
7. MediaPipe WASM 和手势模型来自远程 CDN/Google Storage；
8. 摄像头权限在 WebView2/桌面应用中必须有明确授权和失败降级；
9. 应用离线时远程手势资源会失效；
10. 远程动态脚本不利于 CSP、版本固定和可复现打包。

### 2.7 当前 Claude 就绪状态

只读研究发现：

- 本机 Claude Code 二进制版本：`2.1.317`；
- Claude 桌面应用正在运行；
- 直接从独立 CLI 执行只读打印任务时返回 `Not logged in · Please run /login`；
- 该次 Claude CLI 调用没有读取、修改或提交任何文件；
- 后续由天火在已登录 Claude 会话中明确要求 Claude 读取本文件，是当前最可靠的交接方式；
- 不得声称 Claude 已经审查本路线，除非 Claude 后续实际回读并给出结果。

### 2.8 当前 Notion 规则状态

Notion 根目录权威页：

- 标题：`agent规则`
- 页面：https://app.notion.com/p/40ce2c99423c81f4ac79f820f1ed3907
- 当前生效版本：`v9`
- 时间：`2026-11-10 12:20`（Asia/Shanghai）
- 署名：`claude-code（Claude Code，本机）`

v9 规定：

- 所有 Agent 读取最新版本；
- 最新版本的全部规则对所有 Agent 生效；
- 新规则必须第一时间更新到该页；
- 每次更新新建版本并置顶；
- 新版本必须包含前版全部规则；
- 标题写版本号、Asia/Shanghai 时间和署名；
- 旧版留在历史版本；
- Notion 页面顶部保留来源标签；
- Git/Markdown/Notion 有 Agent 署名约定；
- Git 提交后同一步推送，失败当场说明；
- `git push --force` 仍需用户确认。

研究时 Notion 根目录尚无正式的 `Duo Hub｜多 Agent 协作工作区`。

本文件只记录规划，**没有修改 Notion v9，也没有创建任何 Notion 页面或数据库。**

## 3. 已确定的目标架构原则

### 3.1 Notion 是共同规则与人类可见协作记录真源

目标定义：

- `agent规则`：共同规则真源；
- `Duo Hub｜多 Agent 协作工作区`：会话、分工、工作日志和验收的人类可见真源；
- `taskline.py`：每日任务状态真源；
- Duo Hub 本地数据库：运行事务、断网恢复和待同步队列；
- Git 仓库：代码、设计文档、测试和版本历史真源。

这四者职责不同，不能互相冒充：

| 系统 | 负责 | 不负责 |
|---|---|---|
| Notion `agent规则` | 最新共同规则 | 运行队列、进程状态 |
| Notion Duo Hub 工作区 | 会话、分工、完整可审计日志、成果索引 | 每日任务线唯一状态 |
| `taskline.py` | 每日任务状态、依赖、Git 推送验收 | 保存每条 Agent 对话 |
| 本地 SQLite/outbox | 事务、断网缓冲、幂等同步 | 共同规则、长期人类工作区 |
| Git | 代码与正式文档版本 | 私密会话原文、Token |

### 3.2 不再建立新的共同规则副本

- Duo Hub 不在 Git、`AISharedMemory`、Claude 工作区或 Codex 工作区复制完整 Notion 共同规则；
- 本地 Agent 规则文件只保留“如何找到并读取 Notion 最新规则”的启动指针，以及该 Agent 必须遵守的平台/工具专属规则；
- Duo Hub 每次建立或恢复会话时读取 Notion 最新生效版本；
- 会话保存 `rule_version`、`rule_page_id`、`rule_last_edited_at`、`rule_content_hash`；
- 长时间运行的会话在恢复、新分工或用户纠正时重新检查；
- 用户当轮最新明确纠正立即优先，不等待 Notion 更新。

### 3.3 完整日志的定义

“完整”是完整保存**可观察、可审计、可恢复**的工作轨迹：

必须保存：

- 用户在 Duo Hub 中提交的完整消息；
- 主管 Agent 的任务拆分；
- 发给每个 Agent 的完整可见提示；
- 每个 Agent 返回的完整可见结果；
- 模型、调用方式、开始/结束时间、退出码和用量（能够取得时）；
- 工具调用的名称、目标、结果摘要、错误和产物；
- 状态变化；
- 用户裁决；
- 重试、超时、失败和恢复；
- 文件/提交/页面/产物路径和哈希；
- 最终验收和未完成项。

不保存：

- 模型隐藏思维链、内部不可见推理；
- API Key、Token、Cookie、密码、OTP、密钥原文；
- 与任务无关的隐私；
- 无限制的二进制内容；
- 为了“看起来完整”而重复复制同一内容。

工具输出过长时：

- Notion 事件保存完整的任务相关可见输出或受控附件；
- 页面正文保存摘要、原始产物链接和 SHA-256；
- 不能把秘密先写入再删除，必须在持久化前脱敏。

### 3.4 署名必须区分内容来源和写入者

至少同时保存：

- `actor`：内容是谁产生的；
- `recorded_by`：谁把它写入 Notion；
- `model`：具体模型或 CLI，能够可靠取得时；
- `agent_session_id`：原 Agent 会话标识，能够取得时；
- `source_event_id`：调用链中的原事件。

例：

| 场景 | actor | recorded_by |
|---|---|---|
| Codex 自己回复并写入 | codex | codex |
| Claude 回复，由 Codex 代理写入 | claude | codex |
| Codex 调用 Gemini 后写入 | gemini | codex |
| Claude 调用 Gemini 后写入 | gemini | claude |
| Duo Hub 同步工作器写入系统状态 | system | duo-hub |

不允许把 Gemini 输出写成 Codex 或 Claude 原创，也不允许把代写者误标为内容作者。

## 4. Notion 根目录框架设计

> 本节为待实施设计。本轮未创建。

### 4.1 顶层页面

建议在 Notion 根目录创建：

`Duo Hub｜多 Agent 协作工作区`

页面顶部固定：

- 来源：`codex`（首次创建时）；
- 当前状态；
- 当前 Duo Hub 软件版本；
- 当前生效规则链接；
- 当前默认协作组；
- 最近活跃会话；
- 待同步/失败记录；
- 使用说明；
- 数据库入口。

`agent规则` 继续留在 Notion 根目录，不移动进 Duo Hub 页面；工作区只链接它，避免规则被错误理解为项目私有副本。

### 4.2 数据库一：`Duo Hub｜协作会话`

一条记录代表一次完整协作会话或一个可恢复工作单元。

建议字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| 会话标题 | Title | 人类可读标题 |
| Session ID | Text | 稳定唯一 ID，例如 `dh_20261110_183300_ab12` |
| 状态 | Select | draft / assigned / running / waiting_user / verifying / completed / failed / cancelled |
| 执行状态 | Select | 任务本身状态 |
| 归档状态 | Select | pending_sync / syncing / verified / sync_failed |
| 规则版本 | Text | 如 `v10` |
| 规则哈希 | Text | 当前规则正文哈希 |
| 主控 Agent | Select | codex / claude |
| 参与者 | Multi-select | codex / claude / gemini / openclaw |
| 默认协作组 | Text | 当前建议 `codex+claude` |
| Taskline ID | Text | 对应本地任务线 ID |
| 软件版本 | Text | 如 `0.6.0` |
| 仓库 | URL/Text | GitHub 与本地路径 |
| 分支 | Text | 当前分支 |
| 开始时间 | Date | Asia/Shanghai |
| 结束时间 | Date | 终态时间 |
| 最后事件序号 | Number | 对账用 |
| 事件总数 | Number | 对账用 |
| 最终结果 | Text | 简短结论 |
| 验收状态 | Select | not_started / verifying / accepted / rejected |
| 敏感级别 | Select | normal / private / restricted |
| 最后同步错误 | Text | 仅错误摘要，不放秘密 |

页面正文模板：

1. 用户原始要求；
2. 规则版本和读取证据；
3. 目标、范围、非目标；
4. Agent 分工；
5. 关键决策；
6. 产物；
7. 验证；
8. 错误与恢复；
9. 剩余事项；
10. 最终验收。

### 4.3 数据库二：`Duo Hub｜完整事件与会话日志`

一条记录代表一个不可变的审计事件。

建议字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| Event ID | Title | 全局稳定 ID |
| Session | Relation | 关联协作会话 |
| Seq | Number | 会话内严格递增 |
| 时间 | Date | 原始发生时间 |
| Actor | Select | user / codex / claude / gemini / openclaw / system |
| Recorded By | Select | codex / claude / duo-hub |
| 事件类型 | Select | 见下方事件类型 |
| 方向 | Select | inbound / outbound / internal |
| 模型 | Text | 模型或 CLI |
| Agent Session ID | Text | 原 Agent 会话 |
| Parent Event ID | Text | 调用链父事件 |
| 状态 | Select | pending / running / success / error / timeout / cancelled |
| 内容哈希 | Text | 去重与验收 |
| 隐私级别 | Select | normal / private / redacted / restricted |
| 同步状态 | Select | pending / synced / verified / failed |
| 产物链接 | URL/Text | 页面、文件、Git、报告 |
| 错误码 | Text | 非秘密错误 |

事件类型至少包括：

- `user_message`
- `rule_snapshot`
- `session_started`
- `assignment_created`
- `agent_prompt`
- `agent_output`
- `tool_started`
- `tool_result`
- `artifact_created`
- `decision`
- `status_changed`
- `user_approval`
- `error`
- `retry_scheduled`
- `sync_succeeded`
- `acceptance_result`
- `session_completed`

事件页面正文保存：

- 完整可见内容；
- 脱敏说明；
- 调用参数中的非秘密部分；
- 输出；
- 产物；
- 验证；
- 错误；
- 与前后事件的关系。

### 4.4 为什么只用两个核心数据库

用户要求 Notion 是“简易版工作区”，因此不应一开始建立大量数据库。

不单独建立：

- Agent 数据库；
- 模型数据库；
- 工具数据库；
- 产物数据库；
- 决策数据库。

这些先作为页面说明、Select 属性或事件类型存在。只有实际数据量证明需要拆分时才升级。

### 4.5 根页面推荐视图

- 活跃会话：状态不是终态；
- 等待用户：`waiting_user`；
- 待同步：归档状态不是 `verified`；
- 最近完成；
- 最近错误；
- 当前会话的事件时间线；
- Gemini 事件；
- Claude 事件；
- Codex 事件。

## 5. 拟议 Notion `agent规则` v10 增量

> 本节是待审查草案，不是已经写入 Notion 的规则。
> 正式更新时必须按照现有迭代要求：从 v9 完整复制全部生效规则，在最上方新建 v10，保留历史，并写 Asia/Shanghai 时间与 `codex` 署名。

建议 v10 标题：

`# v10｜2026-11-10 HH:mm｜署名：codex（Codex）`

建议在“多 Agent 共同规则”中加入以下完整含义：

1. `agent规则` 最新生效版本是 Duo Hub 中所有 Agent 的共同规则真源；
2. 每次新建、恢复或重新分工前读取最新规则，并记录版本、编辑时间和哈希；
3. Notion 根目录 `Duo Hub｜多 Agent 协作工作区` 是 Duo Hub 唯一的人类可见协作工作区；
4. 旧 `SHARED_MEMORY.md`、旧共同工作区和旧共享规则副本退出，不再读取、更新或迁移；
5. Duo Hub 的分工、完整可见会话、工具结果、错误、产物和验收均写入 Notion；
6. Codex、Claude 原则上写自己的记录；
7. 代理写入时必须区分 `actor` 与 `recorded_by`；
8. Gemini 无需直接拥有 Notion 连接，由调用 Gemini 的 Codex 或 Claude 完整代写；
9. 本地 SQLite/outbox 只用于事务和断网恢复，不是共同工作区或记忆桥；
10. Notion 写入失败时任务执行状态与归档状态分离，不能把未同步说成已完整归档；
11. 事件使用稳定 ID、顺序号和内容哈希，重试不得重复；
12. 不记录秘密和隐藏推理；
13. `taskline.py` 继续是每日任务状态真源，Notion 不另造冲突任务面板；
14. 规则更新、Notion 框架变更和 Git 变更必须写清 Agent 署名；
15. Git 提交后立即推送；推送失败当场说明；force push 仍需用户确认。

正式更新后必须回读：

- v10 位于最上方；
- v9 全部规则仍在 v10 中；
- 时间是 Asia/Shanghai；
- 署名是 `codex`；
- 新条款存在；
- 历史版本保留；
- 页面没有被截断或误覆盖；
- Notion 版本变化能识别本次更新者。

## 6. 运行时架构

### 6.1 目标数据流

1. 用户创建或恢复 Duo Hub 会话；
2. Rule Loader 读取 Notion 最新规则；
3. 本地数据库创建 Session；
4. 本地事件表追加 `rule_snapshot` 和 `session_started`；
5. Notion Sync Worker 创建/查找 Notion 会话页；
6. 用户任务先写本地事务；
7. 主管生成分工并写事件；
8. Dispatcher 调用具体 Agent Adapter；
9. 每个 prompt、output、error、artifact 先落本地事件；
10. 同步器按顺序写入 Notion；
11. 用户做出裁决；
12. 验证器核对本地事件数、Notion 事件数、最后序号和哈希；
13. 执行状态完成且归档状态 verified 后，才宣称会话完整闭环。

### 6.2 本地数据库只做技术底座

建议新路径：

`%LOCALAPPDATA%\DuoHub\data\duohub.sqlite3`

建议表：

- `sessions`
- `events`
- `sync_outbox`
- `agent_runs`
- `artifacts`
- `settings`（不存秘密）

秘密：

- 不写数据库明文字段；
- 不写仓库；
- 后续应用版使用 Windows Credential Manager 或等价安全存储；
- 首版可通过进程环境提供，但不得打印。

SQLite 需要：

- WAL 模式；
- 外键；
- 唯一约束 `(session_id, seq)`；
- 唯一 `event_id`；
- `content_hash`；
- 同步重试次数和下次重试时间；
- 崩溃后自动恢复 `pending` 事件；
- 归档前对账。

### 6.3 旧协议目录处理

旧路径不再作为新工作区使用。

迁移原则：

- 不直接删除；
- 不继续写共同规则；
- 不把它重命名为新记忆桥；
- 首次迁移前做只读快照和哈希；
- 若存在有价值历史会话，按明确映射导入新 Session/Event；
- 当前空闲会话不能伪装成正式历史成果；
- 迁移完成后由用户决定是否归档或删除；
- 删除仍需单独授权和备份。

## 7. Agent Registry 与适配器

### 7.1 目标接口

每个 Agent 适配器统一提供：

- `id`
- `display_name`
- `enabled`
- `capabilities`
- `health_check()`
- `invoke(request)`
- `cancel(run_id)`
- `collect_result(run_id)`
- `model_info()`
- `workspace_policy`
- `notion_access`

统一请求：

- session ID；
- event ID；
- user task；
- assignment；
- rule snapshot；
- allowed tools；
- workspace；
- timeout；
- privacy class；
- expected artifacts；
- output schema。

统一结果：

- status；
- full visible output；
- model；
- started/ended；
- exit code；
- token/usage（可得时）；
- tool summaries；
- artifacts；
- error；
- raw response reference；
- content hash。

### 7.2 默认参与者

当前默认：

- `codex`：主管、架构与最终整合；
- `claude`：审查、独立实现、长上下文检查；
- `gemini`：下一版本新增的研究/分析/代码参与者；
- `openclaw`：保留旧适配器但默认关闭，不从代码中立即删除。

OpenClaw 是否长期保留，由后续用户决定；当前不应阻碍 Codex＋Claude＋Gemini 主链。

### 7.3 主管不应与记录器耦合

- 当前主管可为 Codex；
- 以后可以切换 Claude；
- 事件记录必须由 Duo Hub 核心层统一完成；
- 不能依赖主管或子 Agent 自觉补日志；
- Agent 自写 Notion 是补充，核心拦截层是完整性的最终保证。

## 8. Gemini 接入路线

### 8.1 首选接入：Gemini CLI Headless

官方 Gemini CLI 支持：

- `-p / --prompt` 非交互调用；
- `--output-format json`；
- `--output-format stream-json`；
- JSON 中包含最终 response、统计和错误；
- stream-json 可提供 init、message、tool_use、tool_result、error、result 事件；
- 标准退出码；
- 使用现有登录或明确配置的认证。

首版推荐：

1. 先检查 Gemini CLI 是否已安装、已登录、版本和真实路径；
2. 使用受限工作目录；
3. 默认禁用自动批准危险工具；
4. 输入 prompt 前创建 `agent_prompt` 事件；
5. 捕获 stdout/stderr；
6. 解析 JSON/JSONL；
7. 将 Gemini 输出记录为 `actor=gemini`；
8. 调用者记录为 `recorded_by=codex` 或 `claude`；
9. 捕获退出码、用量、错误和超时；
10. 结果写入本地事件和 Notion。

### 8.2 后续接入：Gemini API

只有在 CLI 路线不能满足稳定性或需要更细粒度函数调用时再进入 API：

- API Function Calling 只返回结构化工具请求；
- 实际执行工具仍由 Duo Hub 应用负责；
- 所有调用必须经过权限和日志层；
- API Key 不进入仓库和 Notion；
- 要有模型版本、限额和错误处理。

### 8.3 Gemini 代写规则

Gemini 不需要自己打开 Notion：

- Codex 调 Gemini：Codex 负责写入；
- Claude 调 Gemini：Claude 负责写入；
- Duo Hub 统一调用：Duo Hub Sync Worker 负责写入；
- 无论谁写，`actor` 必须是 `gemini`；
- 保存完整可见 prompt、response、用量、错误、产物和调用者；
- Gemini 返回的工具建议不能自动扩大权限。

## 9. Notion 同步工程

### 9.1 认证

正式应用建议使用单用户内部 Notion connection：

- 只授权 `Duo Hub｜多 Agent 协作工作区` 根页及其子项；
- Token 存进安全存储；
- 不提交到 Git；
- 不写 Notion；
- 不输出到日志；
- 连接丢失时显示明确 degraded 状态。

### 9.2 限速

官方 Notion API 当前有：

- 非 Business/Enterprise：每个 connection 每分钟 180 请求，平均约 3 次/秒；
- Business/Enterprise：每分钟 600 请求，平均约 10 次/秒；
- Data source query 还有约 3 次/秒限制；
- Workspace 还有共享限额；
- 429/529 需要遵守 `Retry-After`；
- 重试要有指数退避和 jitter。

设计按较低限额工作：

- 不逐 token 写 Notion；
- 以完成的消息/事件为最小写入单元；
- 本地先持久化；
- 批量、排队和退避；
- 查询前缓存数据库 schema；
- 写入不确定时先按 event ID 查询，再重试；
- 同步最终失败必须可见。

### 9.3 不把 Webhook 作为本地首版依赖

Notion webhook 要求公网 HTTPS endpoint，localhost 不可达。

所以本地桌面应用首版：

- 会话开始读取规则；
- 会话恢复读取规则；
- 新分工前检查 last edited；
- 用户纠正立即生效；
- 不为了 webhook 暴露公网服务。

未来若有受控云端，可选 webhook 并验证 HMAC 签名。

### 9.4 幂等与对账

每个事件：

- 先生成 event ID；
- 本地提交；
- Notion 以 event ID 为唯一键；
- 写入后记录 Notion page ID；
- 重试前查询；
- 完成时比对事件总数、最后 seq 和哈希；
- 只在回读成功后设置 `archive_status=verified`。

## 10. 桌面应用化决定

### 10.1 最终判断

不推倒 HTML。

从下一实施轮开始：

- **按桌面应用架构开发；**
- **继续复用现有 HTML/CSS/JS；**
- **暂不急于出安装包；**
- **Notion＋Gemini 主链跑稳后再封装。**

这不是“继续做网站，最后随便套壳”，而是：

> 现在完成应用内部边界、模块、生命周期和离线数据设计；最后一步才是生成安装程序。

### 10.2 推荐首版：pywebview/WebView2＋PyInstaller onedir

理由：

- 复用 Python 后端；
- 复用 HTML/CSS/JS；
- Windows 使用 WebView2；
- 可在一个应用进程中管理窗口和后端；
- 不再依赖 Chrome `--app`；
- 可以逐步把 HTTP 换成 JS-Python bridge；
- 工程变化小于 Tauri 重写；
- PyInstaller onedir 便于调试和稳定升级。

不建议首个应用版直接 `onefile`：

- 启动时需要解压；
- 崩溃和杀进程时可能留下临时目录；
- 调试更困难；
- Agent CLI、资源、模型和 WebView 依赖较多。

### 10.3 Tauri 的位置

Tauri 2 支持把 PyInstaller 生成的 Python 后端作为 sidecar，长期可以考虑。

但当前立即上 Tauri 会同时引入：

- Rust 工具链；
- Tauri 权限/capability；
- Python sidecar 打包；
- 多架构 binary 命名；
- Notion；
- Gemini；
- Agent 生命周期。

因此不作为当前第一步。等 Windows 应用跑稳、需要跨平台或更严格桌面权限时再评估。

### 10.4 应用化前端重构

建议结构：

`web/`

- `index.html`
- `styles/`
  - `base.css`
  - `layout.css`
  - `components.css`
  - `star-map.css`
- `js/`
  - `main.js`
  - `api/hub_api.js`
  - `state/store.js`
  - `components/agent_panel.js`
  - `components/session_log.js`
  - `components/supervisor_status.js`
  - `features/star_map.js`
  - `features/gesture.js`
  - `utils/render.js`
- `vendor/`
  - 固定版本 MediaPipe/WASM/模型（若保留）

`HubApi` 提供：

- `getState()`
- `createTask()`
- `assign()`
- `confirm()`
- `cancel()`
- `setModel()`
- `getSessions()`
- `getEvents()`
- `getSyncStatus()`
- `retrySync()`

开发期可用 HTTP adapter；应用版换 pywebview adapter，UI 不重写。

### 10.5 应用化后端重构

建议结构：

- `duohub/domain/`
  - `session.py`
  - `event.py`
  - `agent.py`
- `duohub/agents/`
  - `base.py`
  - `codex.py`
  - `claude.py`
  - `gemini.py`
  - `openclaw.py`
- `duohub/storage/`
  - `sqlite.py`
  - `migrations.py`
- `duohub/notion/`
  - `client.py`
  - `schema.py`
  - `sync_worker.py`
  - `redaction.py`
- `duohub/services/`
  - `orchestrator.py`
  - `rule_loader.py`
  - `event_recorder.py`
  - `acceptance.py`
- `duohub/api/`
  - `http.py`（开发期）
  - `desktop_bridge.py`（应用期）
- `duohub/app.py`

现有 `duo_hub.py` 暂作兼容入口，逐步转发到模块，不一次性重写。

## 11. Codex、Claude、天火的协作方式

### 11.1 天火

在项目跑通前：

- 负责明确优先级；
- 决定何时让 Claude 接手；
- 解决 Codex 与 Claude 意见冲突；
- 决定 Notion 正式写入时间；
- 决定 OpenClaw 是否保留；
- 做高风险外部动作的最终批准；
- 不需要承担可由 Agent 完成的普通技术操作。

### 11.2 Codex

建议负责：

- 总体架构；
- Notion 数据模型；
- v10 规则草案与正式更新；
- SQLite/Event/Outbox；
- Notion 同步器；
- 幂等和验收；
- Gemini 日志代理协议；
- 最终集成和事实核验。

### 11.3 Claude

建议负责：

- 独立审查本文件；
- 核对 Claude 工作区和 CLI 真实限制；
- 更新 Claude 自己的启动指针，删除 `SHARED_MEMORY.md` 旧逻辑；
- Agent Adapter 的 Claude 侧实现；
- 前端模块化和动态 Agent 面板；
- 应用壳、WebView2 和安装测试；
- 对 Codex 实现进行独立代码审查。

### 11.4 共享资源串行

以下不能并行写：

- Notion `agent规则`；
- Notion Duo Hub 根页面和数据库 schema；
- Duo Hub 同一个 Git 工作树；
- 同一分支的同一文件；
- 应用配置；
- 凭证存储；
- 运行中的正式服务。

推荐节奏：

1. Codex 完成一项逻辑改动；
2. 测试；
3. 独立提交；
4. 立即推送；
5. Claude 拉取并回读；
6. Claude 开始下一项；
7. Claude 提交并推送；
8. Codex 拉取并验收。

## 12. 版本路线

### 阶段 R0：研究与交接基线

产物：

- 本研究路线；
- 当日工作日志；
- Git 提交与推送；
- 不改 Notion。

完成标准：

- 文档完整；
- 署名 `codex`；
- Git 工作树干净；
- 推送成功；
- Claude 能从 Git 读取。

### 阶段 R1：Notion 框架与 v10

前提：用户明确批准修改 Notion。

产物：

- 根页面；
- 两个核心数据库；
- 页面视图；
- v10 规则；
- Codex 测试会话；
- Claude 回读验证。

### 阶段 R2：核心重构

产物：

- Agent Registry；
- Event Model；
- SQLite；
- Outbox；
- Rule Loader；
- Notion Sync；
- HTTP 兼容层；
- 自动测试。

默认活跃 Agent：Codex＋Claude。

### 阶段 R3：Gemini 主版本

建议软件版本：`0.6.x`（最终版本号由实施时确认）。

产物：

- Gemini CLI Adapter；
- JSON/stream-json 解析；
- Gemini 代写；
- 动态 Agent UI；
- 错误/超时/用量；
- Gemini E2E。

### 阶段 R4：Windows 桌面应用

建议软件版本：`0.7.x` 或 `1.0.0-rc`。

产物：

- pywebview/WebView2；
- PyInstaller onedir；
- 单实例；
- 应用数据目录；
- 安全凭证；
- 启动/退出/重启；
- 崩溃恢复；
- 安装与卸载；
- 日志查看；
- 自动/手动更新策略。

### 阶段 R5：稳定版

完成：

- Codex＋Claude＋Gemini；
- Notion 完整同步；
- 断网恢复；
- 多轮会话；
- 安装应用；
- 长时间运行；
- 故障恢复；
- 完整验收报告。

## 13. 测试与验收

### 13.1 规则

- 新会话读取当前规则；
- 记录版本、时间和哈希；
- 规则更新后新分工能发现；
- 用户纠正即时生效；
- 旧 `SHARED_MEMORY.md` 不再读取。

### 13.2 会话与日志

- 用户消息完整；
- 每个 Agent prompt/output 完整；
- actor/recorded_by 正确；
- seq 连续；
- event ID 唯一；
- 内容哈希匹配；
- 错误和超时存在；
- 产物可打开；
- Notion 回读数量一致。

### 13.3 断网与限速

- Notion 离线仍可安全记录本地事件；
- 显示 pending_sync；
- 恢复网络自动补写；
- 429/529 遵守 Retry-After；
- 重试不重复；
- 同步失败可人工重试；
- 未 verified 不宣称完整归档。

### 13.4 Gemini

- CLI 不存在；
- 未登录；
- 正常 JSON；
- stream-json；
- 超时；
- 非零退出；
- stderr；
- 工具事件；
- 取消；
- 敏感数据拦截；
- 代理写入来源正确。

### 13.5 应用

- 双击启动；
- 单实例；
- 不依赖 Chrome；
- 不弹终端；
- 不误杀无关端口；
- 退出后子进程清理；
- 崩溃后恢复；
- 无网可开；
- WebView2 缺失时明确提示；
- 摄像头拒绝时不影响主功能；
- 资源离线可用；
- 多 DPI；
- 最小化/恢复；
- 重启后会话可恢复。

### 13.6 Git

- 一项逻辑改动一个提交；
- 提交有 `[codex]` 或 `[claude-code]`；
- footer 有 `Agent: ...`；
- 提交后立即推送；
- 不 force push；
- 不提交配置秘密；
- 提交前后工作树回读。

## 14. 风险清单

| 风险 | 后果 | 对策 |
|---|---|---|
| Notion 变成第二任务线 | 状态冲突 | taskline 管状态，Notion 管协作详情 |
| 多 Agent 同写 Notion schema | 结构冲突 | 天火协调，串行写 |
| 每 token 写 Notion | 限速、成本、重复 | 完成事件后批量同步 |
| 写入超时后盲目重试 | 重复页面 | event ID 查询后重试 |
| Gemini 无 Notion | 日志缺失 | 调用者代理写入 |
| 代理写错署名 | 审计失真 | actor/recorded_by 分离 |
| 隐藏推理被当日志 | 隐私与不可得 | 仅记录可见输出和工具结果 |
| 秘密进入日志 | 安全事故 | 持久化前脱敏 |
| 继续写死三方 UI | Gemini 加入返工 | Agent Registry＋动态面板 |
| 立即 Tauri 重写 | 范围爆炸 | 先 pywebview，后评估 Tauri |
| Chrome app 继续长期使用 | 生命周期不稳 | 应用壳统一管理 |
| 在线 MediaPipe | 离线失败、版本漂移 | 固定本地资源或可选关闭 |
| 多 Agent 同一 Git 工作树 | 覆盖改动 | commit/push/pull 串行 |
| 旧路径 `C:\Users\25406` | 启动失败 | 枚举真实路径并迁移配置 |
| 误杀端口进程 | 影响其他服务 | 校验进程身份，不按端口强杀 |
| Notion 规则页越来越大 | 解析慢 | 解析当前版本区段，历史不注入 prompt |

## 15. 明确不做

- 本轮不改 Notion；
- 不删除旧协议目录；
- 不恢复 `SHARED_MEMORY.md`；
- 不把本地缓存包装成新记忆桥；
- 不把 Notion 当作 taskline 替代；
- 不立即重写全部前端；
- 不立即切 Tauri；
- 不把 Gemini 输出冒充 Codex/Claude；
- 不记录隐藏推理；
- 不提交密钥；
- 不启动、重启或停止 Duo Hub 正式服务；
- 不执行 `launch/start/run/serve` 入口做“语法检查”。

## 16. Claude 接手清单

Claude 在天火明确要求后：

1. 拉取 `master`；
2. 回读当前 HEAD；
3. 完整阅读本文件；
4. 阅读 `work_logs/2026-11-10.md`；
5. 阅读当前 `README.md`、`duo_hub.py`、`web/index.html`、`web/app.js`、启动脚本；
6. 回读自己当前 `CLAUDE.md`；
7. 不读取不存在的 `SHARED_MEMORY.md`；
8. 不修改 Notion，除非天火明确批准；
9. 先向天火汇报独立审查、异议和建议；
10. 获批后只实施分配给 Claude 的逻辑改动；
11. 提交、推送并提供测试和 commit 证据；
12. 不覆盖 Codex 署名；
13. 把自己新增内容标成 `claude-code`；
14. 共享文件修改遵循串行锁。

## 17. 官方资料

- Notion `agent规则`：https://app.notion.com/p/40ce2c99423c81f4ac79f820f1ed3907
- Notion API Request limits：https://developers.notion.com/reference/request-limits
- Notion Webhooks：https://developers.notion.com/reference/webhooks
- Notion Authorization：https://developers.notion.com/guides/authorization/overview
- Gemini CLI Headless：https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/headless.md
- Gemini CLI Automation：https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/tutorials/automation.md
- Gemini API Function Calling：https://ai.google.dev/gemini-api/docs/function-calling
- pywebview：https://pywebview.idepy.com/en/guide/
- PyInstaller：https://pyinstaller.org/en/stable/operating-mode.html
- Tauri Sidecar：https://v2.tauri.app/develop/sidecar/

## 18. 研究结论

最终路线不是“继续做网页”或“现在全部重写应用”二选一，而是：

1. Notion 最新共同规则继续作为 Duo Hub 正式规则；
2. Notion 根目录建立简易协作工作区；
3. 旧共同工作区和 `SHARED_MEMORY.md` 完全退出；
4. 本地只保留技术事务缓存；
5. Codex＋Claude 是当前主协作组；
6. 下一软件版本重点接入 Gemini；
7. Gemini 由调用者代理写 Notion；
8. 所有可见会话和工作日志形成完整事件链；
9. 现有 HTML/CSS/JS 保留；
10. 从下一实现轮开始按桌面应用架构重构；
11. Notion/Gemini 核心跑稳后用 pywebview/WebView2＋PyInstaller onedir 出 Windows 应用；
12. 天火在项目跑通前担任 Codex 与 Claude 的协调者。

---

署名：`codex`
作者：Codex
日期：2026-11-10（Asia/Shanghai）
