# Duo Hub｜Gemini CLI 与 Antigravity 对比（2026-11-17）

## 结论

当前 Duo Hub 默认继续使用：

```text
逻辑席位 gemini → Antigravity CLI → Gemini 4 Hydrogen Medium
```

Gemini CLI 保留为备用 provider，等用户完成 Google 登录、API Key 或 Vertex AI 认证后，再做同任务、同模型档位的第二轮质量对比。

## 本机状态

| 入口 | 版本/状态 | 真实生成 | 当前用途 |
|---|---|---:|---|
| Gemini CLI | 0.68.0；已安装、未配置认证 | 否 | 备用 Adapter，等待认证 |
| Antigravity CLI | 1.5.10；已登录 | 是 | Duo Hub 默认自动化入口 |
| Antigravity App | 2.30.0；界面显示 `Hi Jeff.`，已选 Gemini 4 Hydrogen Medium | 本轮未通过 App 发送消息 | 人工交互与观察；不作为后端自动化接口 |

Antigravity App 当前显示 `Restart to Update`。本轮只核验，不代替用户点击更新或重启。

## 同任务实测

### 1. Gemini CLI：精确文本

- 命令模式：headless JSON、plan、无工具；
- 模型：`gemini-3.5-flash`；
- 结果：约 1.8 秒退出；
- 退出码：41；
- 原因：尚未在 Gemini CLI 设置认证方式；
- 结论：安装成功不等于可生成，当前不能进入质量和稳定性比较。

### 2. Antigravity CLI：结构化 JSON

- 模型：`gemini-4-hydrogen-medium`；
- 模式：plan；
- 结果：`SUCCESS`，退出码 0；
- 返回：`{"result":"DUO_COMPARE_JSON_OK","count":3}`；
- 进程墙钟时间：约 12.4 秒；provider 报告生成时间约 5.4 秒；
- 总 token：10721；
- conversation ID、usage、状态和正文均可结构化审计。

### 3. Antigravity CLI：读取仓库版本

第一条含糊提示只说“读取 VERSION 并回答”。plan 模式把它理解成实施流程，耗时约 28 秒，创建 Antigravity 自己的 plan artifact，并要求确认，没有返回版本号。

第二条提示明确写明“这是只读事实问题，不是实施请求；不要创建计划，不要修改工作区，只返回答案”后：

- 结果：`SUCCESS`，退出码 0；
- 返回：`DUO_VERSION=0.6.1`；
- 进程墙钟时间：约 13.8 秒；provider 报告生成时间约 6.0 秒；
- 总 token：12884。

因此 Duo Hub 的分析模式提示已固化“非实施、不要创建实现计划、只返回答案和必要证据”。这比单纯依赖 `--mode plan` 更稳定。

固化后又通过 Duo Hub `0.6.2` 完成一次集成回归：API 提交“读取当前仓库 VERSION，只返回精确答案”，最终返回 `DUO_VERSION=0.6.2`，provider 为 `antigravity-cli`、退出码 0、event_seq 2，证明约束在真实 Adapter 主链中生效。

## 使用体验判断

### Antigravity CLI 更顺手的地方

- 当前账号链路已经认证，无需额外密钥或登录；
- JSON 输出包含 conversation ID、usage、耗时和状态，适合 Duo Hub 事件审计；
- 支持模型选择、plan 模式、超时和可取消子进程；
- 已通过真实回包、服务重启恢复、运行中取消和旧会话隔离验收。

### Antigravity CLI 的注意点

- plan 模式有较强的“先写计划、等确认”倾向，事实问答必须明确声明不是实施请求；
- token 用量较高；
- App 与 CLI 版本并不相同，不能用 App 的更新提示推断 CLI 已更新或反之。

### Gemini CLI 的当前边界

- 官方 headless JSON、session 和工具事件接口更贴近长期标准化 Adapter；
- 但本机尚未认证，当前不能生成，不能把 `--list-models` 成功当成可用；
- 完成认证前，不应切换 Duo Hub 默认 provider。

## 决策

1. Phase 3 选择 Antigravity CLI 作为当前默认 provider。
2. Antigravity App 只用于人工交互和观察，不用于 Duo Hub 后端自动化。
3. Gemini CLI Adapter 保留，但 UI 和日志必须明确显示其未认证状态。
4. Windows App 打包阶段继续复用统一 Agent Registry，不把 provider 写死进 UI。
5. 大创项目练手时先走 Antigravity CLI；待 Gemini CLI 认证后，再用同一组任务复测，不重写业务层。
