# Multica CLI v0.13.0 差异与验证

2026-11-26 在 mac-work 递归对比官方 v0.12.1（`fc8028d76`）与 Homebrew v0.13.0（`35b54a374`）的可见命令和参数。共同命令及其风险见 [v0.12.1 差异](cli-v0.12.1.md)和 [v0.11.0 总表](cli-v0.11.0.md)。[官方发布说明](https://github.com/multica-ai/multica/releases/tag/v0.13.0) · [固定版 CLI 文档](https://github.com/multica-ai/multica/blob/v0.13.0/CLI_AND_DAEMON.md)

## Issue 阻塞关系

| 命令（省略 `multica`） | 类别 | 新增能力 |
|---|---|---|
| `issue list --blocked` | R | 筛选仍在等手动阻塞项或较早阶段任务的 Issue。 |
| `issue create --blocked-by <issue>` | W/X | 新建 Issue 时设置前置项。参数可重复，接受 Issue 编号或 UUID。 |
| `issue update <issue> --blocked-by <blocker>`、`--remove-blocked-by <blocker>` | W/X | 增删手动阻塞项。两参数均可重复。阶段阻塞随父任务与阶段设置计算。 |

- 用 `issue get <issue> --output json` 核对 `blocked_by`、`blocked_count` 和 `blocking`。用 `blocked_by[].via` 区分手动（`manual`）和阶段（`stage`）。先核目标实例确实支持阻塞关系。[Issue CLI 参数](https://github.com/multica-ai/multica/blob/35b54a3742bb51bdf5ffa688655367ec98044862/server/cmd/multica/cmd_issue.go#L4296-L4320)
- 前置项未完成时，新建、指派或状态变更产生的自动派发会等待。全部解阻后，非 `backlog` 的 Issue 可自动派发给 Agent，成员指派可发通知。直接点名或回复评论仍可能启动 Run。移除最后一个阻塞前核对指派、状态与派发授权，变更后读回阻塞关系和实际 Run。[官方 Issue 操作](https://github.com/multica-ai/multica/blob/v0.13.0/CLI_AND_DAEMON.md#create-issue)

## Squad 直接交接

| 命令（省略 `multica`） | 类别 | 新增能力 |
|---|---|---|
| `squad update <squad> --handoff-mode leader\|direct` | A | 设置工作区 Squad 的交接方式。 |
| `squad briefs <squad> [--agent <agent>] --output json` | R | 预览 Agent 实际收到的 Squad 指引。需要 Squad 管理权限，核对单一成员时指定 `--agent`。 |

- 用 `squad get <squad> --output json` 核对 `handoff_mode`，并核成员角色。缺少模式字段时再核目标服务端能力。默认 `leader` 由负责人接收成员回复。获准配置为 `direct` 后，成员可点名下一位 Squad 成员完成交接。回合过多、24 小时交接次数达上限、成员 Run 失败或没有点名接手人时，平台交回负责人。[官方 Squad 交接](https://github.com/multica-ai/multica/blob/v0.13.0/CLI_AND_DAEMON.md#squads)
- 需要验证交接时，在原 Issue 核对实际接手 Agent、Run 和回执。Squad 交接模式用于选择下一位接手人，项目工作流状态与独立复审要求仍按原项目约定执行。

## 本轮验证

| 项目 | 2026-11-26 证据 |
|---|---|
| 腾讯云服务端 | 前后端均为 `v0.13.0`，API readiness 和 Web 入口通过。[部署回执](https://github.com/CF-FE/multica-4-dot/blob/af91454f3938581d015b1060c2fdd5859cac127c/docs/tencent-upgrade.md#2026-11-26-升级回执) |
| mac-work CLI 与 Daemon | CLI 实读为 `0.13.0`。运行中 Daemon 的 `cli_version` 为 `0.13.0`，读回 1 个工作区和 0 个在途任务。本轮原卡领单与回传待验，既有实单见 [v0.12.1 历史记录](cli-v0.12.1.md#mac-work-v0121-与腾讯云-v0110)。 |
| Vultr MCP | 仓库 MCP 包版本为 `0.1.0`，本地契约与网关测试共 87 项通过。部署中的 MCP 已对腾讯云读通项目列表、项目、Issue、指定 Run 与 Run 列表。Vultr 发布提交和现网写入行为待验。当前工具的 Issue 投影与更新参数没有暴露阻塞关系，也未提供 Squad 模式管理。 |
| 新功能写入 | 已核对目标 CLI 帮助和官方固定版文档。阻塞变更的自动派发、Squad 实际交接及回执须在有授权的业务卡或隔离实例验证。 |
