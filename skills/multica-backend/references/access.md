# Multica 认证、调用与控制

参考基线：Multica v0.9.0；这是设计与离线核对，不是用户实例上线证据。官网在线 CLI 指南可能比发行版更新。CLI 的实际版本与 `--help`、服务器部署摘要及本页固定源码均须留痕。

## 认证分层

| 身份 | 用途 | 边界 |
|---|---|---|
| Web 会话 | 人工浏览器操作 | HttpOnly 会话 Cookie 与 CSRF 针对浏览器；不复制到脚本、MCP 或聊天 |
| 个人访问令牌（PAT，`mul_`） | CLI/Daemon 登录、受控 REST 访问 | 继承账号权限，不是只读 token；用隔离账号、明确有效期和撤销路径。服务器端凭据存储；不回传给 Dot 或模型 |
| Agent Run 临时令牌（`mat_`） | 运行中，由平台注入 | 绑定当前 Run、Agent、workspace 和用户，上游文档上限 24h；不把它当作长期 MCP 凭据 |
| 内部 daemon/service 令牌 | 运行协议和内部服务 | 不模仿、不签发、不拿来做业务 API；Decision Service 与 Task Mailbox 各自认证，不能互换 |

发送 PAT 时用 `Authorization: Bearer <PAT>`；workspace 级 API 按路由传 `X-Workspace-ID: <UUID>`。这个 header 只选范围，不授予访问权。凭据只允许走验证过的 TLS 或已确认加密的受控私网；首跳授权与私网传输分开。不要跟随去往其他主机的重定向，也不要把凭据、调试输出或配置原样写到日志。

## CLI：人工接入和排障

已配置的试点 profile 的只读示例（所有标识为占位）：

```bash
multica version
multica --profile pilot auth status
multica --profile pilot workspace list --output json
multica --profile pilot --workspace-id "$WS_ID" issue get "$ISSUE" --output json
multica --profile pilot --workspace-id "$WS_ID" issue runs "$ISSUE" --full-id --output json
multica --profile pilot --workspace-id "$WS_ID" runtime list --output json
multica --profile pilot daemon status --output json
```

- `auth status` 仅辅助诊断；未登录、过期可能也返回进程退出码 0。用服务端身份读回及目标 workspace 查询证实权限。
- 管理 CLI 只读查询不需要本机启动 Daemon。首次设置是有副作用的独立步骤：经授权另设 profile 的 `config set server_url` / `app_url`，然后用交互式 `login --token`；不要把令牌跟在命令上。`setup self-host` 还会带登录和启动 Daemon，不是只读连接检查。
- Daemon 是工作机执行代理，负责领取运行并调用同机 Codex/Kimi。这里只列诊断入口，不从云端通用代理暴露启停、注册、升级、日志、自动启动和配置写入。
- 阅读 `issue run-messages <RUN_UUID> --issue <ISSUE>` 必须另有读取内容的必要性与权限；默认不作为工具参数或输出透传。

## REST：首选窄接口

| 请求 | 证据等级 | 用途 |
|---|---|---|
| `GET /health`、`GET /readyz` | 固定路由 / 自托管指南 | 区分到达 API 与 DB/迁移就绪；都不是身份授权证明 |
| `GET /api/me` | 官方认证示例 | 核对实际调用身份，只返回最小字段 |
| `GET /api/issues` | 官方认证示例 | 带 workspace、固定项目及有界分页；仅必要时列出 |
| `GET /api/issues/{id}` | 固定版源码 | 按服务返回的 Issue 标识精确读取，一期用 UUID |
| `GET /api/issues/{id}/task-runs` | 固定版源码 | 限定 Issue 的 Run 列表，用授权范围内实际 Run UUID 匹配；不假设全局 `GET /api/runs/{id}` |
| `GET /api/issues/{id}/active-task` | 固定版源码 | 补充排查，空 active 不推出没有历史或没有终态异常 |
| `GET /api/tasks/{taskId}/messages` | 固定版源码；内容敏感 | 非默认工具，先核对 Run 和 Issue 关系再做必要摘要 |

使用固定实例的 origin，不接受用户输入 URL；path ID 结构化校验，不拼 shell。版本锁定时保存脱敏 fixture 和响应字段契约。HTTP 401/403、404、429、网络超时、5xx、响应结构漂移和分页不完整分别处理；404 不自动推断对象从未存在。对限流或网络异常只对允许的读操作做有限重试，写超时不盲重试。

## 控制动作：仅做行为参考

| 操作 | 已知影响与停止线 |
|---|---|
| `issue assign` / `status` / `update` | 可能写 Issue 或启动 Run；在版本支持时每个必要命令各传 `--no-start`，不能据此认定无任何业务副作用 |
| `issue comment add` | 普通评论可能触发执行或进入当前 Run；记录时只考虑经沙箱验证的 `/note`，写前写后比对 Run 与活动记录 |
| `issue cancel-task <RUN_UUID> --issue <ISSUE>` | 取消影响原 Run；回读平台状态并区分实际进程退出；并不回滚外部影响 |
| `issue rerun-task <RUN_UUID> --issue <ISSUE> [--fresh]` | 新建 Run，通常依据原执行的 Agent/触发源；默认尝试续用会话，fresh 新会话/目录。先查自动重试和真实产物，不依赖当前负责人推断目标 |
| 权限、秘密、Daemon、触发规则、删除、批处理 | 设计上不进入首版 MCP；不提供任意 CLI、任意 HTTP 或 shell 入口 |

来源：[固定版 CLI](https://github.com/multica-ai/multica/blob/8cd8a2db978d532d8627c78cd29f05deab6c6f17/CLI_AND_DAEMON.md) · [固定版路由](https://github.com/multica-ai/multica/blob/8cd8a2db978d532d8627c78cd29f05deab6c6f17/server/cmd/server/router.go) · [固定版 Issue 命令](https://github.com/multica-ai/multica/blob/8cd8a2db978d532d8627c78cd29f05deab6c6f17/server/cmd/multica/cmd_issue.go) · [认证](https://multica.ai/docs/auth-tokens) · [指派](https://multica.ai/docs/assigning-issues) · [评论路由](https://multica.ai/docs/mentioning-agents) · [Run 重试](https://multica.ai/docs/tasks)
