# Multica CLI v0.12.1 差异与实测

2026-11-24 对 mac-work 的 `multica 0.12.1`（`fc8028d76`，darwin/amd64）与 v0.11.0 递归读取 `--help`。以下列出新增可见操作与现有命令标志的差异。共同命令和风险分类沿用 [v0.11.0 总表](cli-v0.11.0.md)。具体参数读当前二进制的 `--help`。[v0.12.1 发布说明](https://github.com/multica-ai/multica/releases/tag/v0.12.1) · [固定源码](https://github.com/multica-ai/multica/tree/v0.12.1/server/cmd/multica)

## 新增操作

| 命令（省略 `multica`） | 类别 | 用途与边界 |
| --- | --- | --- |
| `inbox count` | R* | 当前身份的未读计数。 |
| `inbox read [<id>...]`、`inbox unread <id>...` | W | 改变已读状态。按通知标识操作；`read` 也支持按 Issue 或批量操作。 |
| `inbox archive [<id>...]`、`inbox unarchive <id>...` | W | 归档或恢复通知。核对作用范围，批量归档需要 `--yes`。 |
| `inbox snooze <id>... --until <time>`、`inbox unsnooze <id>...` | W | 暂缓通知或结束暂缓。 |
| `issue edit-description <id>` | W | 精确替换描述片段。提供当前原文和新文本，需多处替换时才用 `--replace-all`。 |
| `project overview <id>`、`project progress <id>`、`project activity <id>` | R | 项目概览、进度和活动。活动可用 `--before`、`--limit` 控制范围。 |
| `quick-action list`、`quick-action get <id-or-name>` | R | 查看当前身份可见的快捷操作。 |
| `quick-action create`、`quick-action update <id-or-name>`、`quick-action archive <id-or-name>`、`quick-action restore <id-or-name>` | W | 管理快捷操作定义。 |
| `quick-action delete <id-or-name>` | D | 删除指定快捷操作。 |
| `quick-action run <id-or-name> <issue-id>` | X | 在原卡投递渲染后的评论，可以触发 Agent 或 Squad。用 `--dry-run` 预览正文和点名对象，真实执行前核对本次授权。 |

## 现有命令新增参数

- `inbox list` 增加 `--archived`、`--issue`、`--since`、`--snoozed`、`--unread`。读取通知用 `list` 或 `count`，改变通知状态需另有授权。
- `issue comment add` 增加 `--idempotency-key`。在支持的服务端，同一请求复用同键。v0.12.1 CLI 在 Agent Run 内还可从 Run、Issue、父评论、正文和附件派生键。旧服务端可能忽略该键，腾讯云 v0.11.0 以原评论和对应 Run 的读回对账为准。[官方评论重试说明](https://multica.ai/docs/cli#common-issue-operations)
- `issue update` 增加 `--description-base-revision`，`skill update`、`skill files upsert/delete` 增加 `--base-revision`。需要并发保护时先确认服务端支持对应修订条件，再用读回的修订号。出现冲突则重新读取目标和合并变更。

## mac-work v0.12.1 与腾讯云 v0.11.0

| 验证项 | 结果 |
| --- | --- |
| CLI 查询 | 已读回 `cloud-work`、既有 Issue、Run 和原生评论。 |
| Daemon 重启与连接 | 已核重启前无在途任务。重启后原 Codex、Kimi、Claude runtime ID 在线并收到新心跳。 |
| 原卡实单 | CLOU-24 只有一条本次 Run。mac-work Codex 已领单、执行并回传三条实际命令输出，摘要与本机独立计算一致。该次回传为调用 `--content-file` 临时落盘后清理。只读复验用[直接传入正文](access.md#daemon-重启与原卡验证)。 |
| 新增只读命令 | `inbox count` 返回计数，`quick-action list` 返回空列表，快捷操作的真实执行待核。可读的运行时验证项目上，`project overview/progress/activity` 均返回资源未找到，查询继续用 `project get` 和 `issue list --project` 等已验证入口。 |

服务端写入和新端点以实际目标版本的支持情况为准。CLI 帮助只证明当前二进制暴露该入口。升级后的回执核对见[认证与调用](access.md)。
