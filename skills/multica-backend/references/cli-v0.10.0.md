# Multica CLI 命令总表（上游 v0.10.0）

以实际安装的 `multica 0.10.0 (commit: 2fcb424b7, built: 2026-11-16T10:27:22Z)`（darwin/amd64）及 [固定源码提交](https://github.com/multica-ai/multica/commit/2fcb424b72b024f65161809081009063846ea44d)为基线。2026-11-18 递归采集 `--help`，并对照根注册和隐藏入口。本表核对的是 CLI 的命令形状与可能副作用。实际执行以目标服务器版本、账号角色、对象权限及本次授权为准。

共 **207 个业务操作入口**，含同时可执行查询和子命令的 `issue pull-requests <id>`。另有 45 个命令组（不计根），其中 `setup` 本身也会执行。根帮助未显示 `environment` 组，按显式路径核对其 3 个操作。隐藏、别名与内部入口见表后。旧版见 [v0.9.0 历史总表](cli-v0.9.0.md)。

## 风险分类

| 标记 | 含义 |
| --- | --- |
| R | 查询。检查对象范围、字段投影、分页和权限。 |
| R* | 敏感或本机读。按需取证并脱敏，如环境、日志、聊天或工具轨迹。 |
| W | 业务写入或上传。检查可能的联动条件。 |
| X | 可能启动、停止、干预执行或配置未来触发。 |
| A | 权限、接入、运行配置或组织级管理变更。 |
| D | 删除、撤销或较大范围的破坏性变更，按具体对象核对。 |
| L | 本机、凭据或账号操作。 |

表中按命令路径与位置参数列出。用对应版本的 `--help` 查 flags。写入、派发和回退需要对应授权。

## 命令入口

### `multica agent`

| 命令 / 位置参数 | 类别 |
| --- | --- |
| `multica agent archive <id>` | A |
| `multica agent avatar <id>` | W |
| `multica agent copy <source-agent-id>` | W |
| `multica agent create` | W |
| `multica agent env get <agent-id>` | R* |
| `multica agent env set <agent-id>` | A |
| `multica agent get <id>` | R |
| `multica agent list` | R |
| `multica agent mcp add <agent-id> <server-id>` | A |
| `multica agent mcp disable <agent-id> <server-id>` | A |
| `multica agent mcp enable <agent-id> <server-id>` | A |
| `multica agent mcp list <agent-id>` | R |
| `multica agent mcp remove <agent-id> <server-id>` | A |
| `multica agent restore <id>` | W |
| `multica agent skills add <agent-id>` | W |
| `multica agent skills list <agent-id>` | R |
| `multica agent skills set <agent-id>` | W |
| `multica agent tasks <id>` | R |
| `multica agent update <id>` | W |

### `multica autopilot`

| 命令 / 位置参数 | 类别 |
| --- | --- |
| `multica autopilot create` | X |
| `multica autopilot delete <id>` | D |
| `multica autopilot get <id>` | R* |
| `multica autopilot list` | R |
| `multica autopilot runs <id>` | R |
| `multica autopilot trigger <id>` | X |
| `multica autopilot trigger-add <autopilot-id>` | X |
| `multica autopilot trigger-delete <autopilot-id> <trigger-id>` | D |
| `multica autopilot trigger-list <autopilot-id>` | R* |
| `multica autopilot trigger-rotate-url <autopilot-id> <trigger-id>` | A |
| `multica autopilot trigger-update <autopilot-id> <trigger-id>` | X |
| `multica autopilot update <id>` | X |

### `multica chat`

| 命令 / 位置参数 | 类别 |
| --- | --- |
| `multica chat history` | R* |
| `multica chat thread [id]` | R* |

### `multica issue`

| 命令 / 位置参数 | 类别 |
| --- | --- |
| `multica issue assign <id>` | X |
| `multica issue batch update <id>...` | X |
| `multica issue cancel-task <run-id>` | X |
| `multica issue children <id>` | R |
| `multica issue comment add <issue-id>` | X |
| `multica issue comment delete <comment-id>` | D |
| `multica issue comment list <issue-id>` | R* |
| `multica issue comment resolve <comment-id>` | W |
| `multica issue comment unresolve <comment-id>` | W |
| `multica issue comment update <comment-id>` | W |
| `multica issue create` | X |
| `multica issue delete <id>...` | D |
| `multica issue get <id>` | R |
| `multica issue label add <issue-id> <label-id>` | W |
| `multica issue label list <issue-id>` | R |
| `multica issue label remove <issue-id> <label-id>` | W |
| `multica issue list` | R |
| `multica issue metadata delete <issue-id>` | D |
| `multica issue metadata get <issue-id>` | R* |
| `multica issue metadata list <issue-id>` | R* |
| `multica issue metadata set <issue-id>` | W |
| `multica issue property list <issue-id>` | R |
| `multica issue property set <issue-id>` | W |
| `multica issue property unset <issue-id>` | W |
| `multica issue pull-requests <id>` | R |
| `multica issue pull-requests link <issue> <pr-url>` | W |
| `multica issue pull-requests unlink <issue> <pr>` | W |
| `multica issue reorder <id>` | W |
| `multica issue rerun <id>`（隐藏） | X |
| `multica issue rerun-task <run-id>` | X |
| `multica issue run-messages <run-id>` | R* |
| `multica issue runs <issue-id>` | R |
| `multica issue search <query>` | R |
| `multica issue status <id> <status>` | X |
| `multica issue subscriber add <issue-id>` | W |
| `multica issue subscriber list <issue-id>` | R |
| `multica issue subscriber remove <issue-id>` | W |
| `multica issue timeline <id>` | R |
| `multica issue update <id>` | X |
| `multica issue usage <issue-id>` | R |
| `multica issue wakeup checkin <issue-id> <wakeup-id>` | W |
| `multica issue wakeup create <issue-id>` | X |
| `multica issue wakeup delete <issue-id> <wakeup-id>` | D |
| `multica issue wakeup disable <issue-id> <wakeup-id>` | W |
| `multica issue wakeup events` | R |
| `multica issue wakeup get <issue-id> <wakeup-id>` | R |
| `multica issue wakeup list <issue-id>` | R |
| `multica issue wakeup runs <issue-id> <wakeup-id>` | R |
| `multica issue wakeup trigger <issue-id> <wakeup-id>` | X |
| `multica issue wakeup update <issue-id> <wakeup-id>` | X |

### `multica issue-status`

| 命令 / 位置参数 | 类别 |
| --- | --- |
| `multica issue-status archive <key-or-name>` | A |
| `multica issue-status create` | A |
| `multica issue-status get <key-or-name>` | R |
| `multica issue-status list` | R |
| `multica issue-status update <key-or-name>` | A |

### `multica label`

| 命令 / 位置参数 | 类别 |
| --- | --- |
| `multica label create` | W |
| `multica label delete <id>` | D |
| `multica label get <id>` | R |
| `multica label list` | R |
| `multica label update <id>` | W |

### `multica project`

| 命令 / 位置参数 | 类别 |
| --- | --- |
| `multica project archive <id>` | A |
| `multica project create` | W |
| `multica project delete <id>` | D |
| `multica project get <id>` | R |
| `multica project list` | R |
| `multica project member add <project-id> <member>...` | A |
| `multica project member list <project-id>` | R |
| `multica project member remove <project-id> <member>` | A |
| `multica project resource add <project-id>` | W |
| `multica project resource list <project-id>` | R |
| `multica project resource remove <project-id> <resource-id>` | W |
| `multica project resource update <project-id> <resource-id>` | W |
| `multica project restore <id>` | A |
| `multica project status <id> <status>` | W |
| `multica project update <id>` | W |
| `multica project workflow get <project-id>` | R |
| `multica project workflow set <project-id> <workflow&#124;default>` | A |

### `multica property`

| 命令 / 位置参数 | 类别 |
| --- | --- |
| `multica property archive <id-or-name>` | A |
| `multica property create` | A |
| `multica property get <id-or-name>` | R |
| `multica property list` | R |
| `multica property unarchive <id-or-name>` | A |
| `multica property update <id-or-name>` | A |

### `multica repo`

| 命令 / 位置参数 | 类别 |
| --- | --- |
| `multica repo add [url]...` | A |
| `multica repo checkout <url>` | L |
| `multica repo list` | R |
| `multica repo remove [url]...` | A |

### `multica skill`

| 命令 / 位置参数 | 类别 |
| --- | --- |
| `multica skill create` | W |
| `multica skill delete <id>` | D |
| `multica skill files delete <skill-id> <file-id>` | D |
| `multica skill files list <skill-id>` | R* |
| `multica skill files upsert <skill-id>` | W |
| `multica skill get <id>` | R* |
| `multica skill import` | A |
| `multica skill label add <skill-id> <label-id>` | W |
| `multica skill label list <skill-id>` | R |
| `multica skill label remove <skill-id> <label-id>` | W |
| `multica skill list` | R |
| `multica skill refresh <id>` | A |
| `multica skill search <query>` | R |
| `multica skill update <id>` | W |

### `multica squad`

| 命令 / 位置参数 | 类别 |
| --- | --- |
| `multica squad activity <issue-id> <outcome>` | W |
| `multica squad create` | W |
| `multica squad delete <squad-id>` | A |
| `multica squad get <squad-id>` | R |
| `multica squad list` | R |
| `multica squad member add <squad-id>` | A |
| `multica squad member list <squad-id>` | R |
| `multica squad member remove <squad-id>` | A |
| `multica squad member set-role <squad-id>` | A |
| `multica squad update <squad-id>` | W |

### `multica view`

| 命令 / 位置参数 | 类别 |
| --- | --- |
| `multica view create` | W |
| `multica view delete <view>` | D |
| `multica view duplicate <view>` | W |
| `multica view get <view>` | R |
| `multica view issues <view>` | R |
| `multica view list` | R |
| `multica view update <view>` | W |

### `multica workflow`

| 命令 / 位置参数 | 类别 |
| --- | --- |
| `multica workflow create` | W |
| `multica workflow delete <workflow>` | D |
| `multica workflow get <workflow>` | R |
| `multica workflow handoff set <workflow> <status-key>` | A |
| `multica workflow list` | R |
| `multica workflow update <workflow>` | W |

### `multica workspace`

| 命令 / 位置参数 | 类别 |
| --- | --- |
| `multica workspace create` | A |
| `multica workspace get [workspace-id&#124;slug&#124;prefix]` | R |
| `multica workspace list` | R |
| `multica workspace mcp add <server-name> [workspace-id&#124;slug&#124;prefix]` | A |
| `multica workspace mcp list [workspace-id&#124;slug&#124;prefix]` | R |
| `multica workspace mcp remove <server-id> [workspace-id&#124;slug&#124;prefix]` | A |
| `multica workspace mcp update <server-id> [workspace-id&#124;slug&#124;prefix]` | A |
| `multica workspace member invite <email> [workspace-id&#124;slug&#124;prefix]` | A |
| `multica workspace member list [workspace-id&#124;slug&#124;prefix]` | R* |
| `multica workspace switch <workspace-id&#124;slug&#124;prefix>` | L |
| `multica workspace update [workspace-id&#124;slug&#124;prefix]` | A |

### `multica daemon`

| 命令 / 位置参数 | 类别 |
| --- | --- |
| `multica daemon autostart disable` | L |
| `multica daemon autostart enable` | L |
| `multica daemon autostart status` | R |
| `multica daemon disk-usage` | R* |
| `multica daemon logs` | R* |
| `multica daemon probe-runtimes`（隐藏） | R* |
| `multica daemon restart` | L |
| `multica daemon start` | L |
| `multica daemon status` | R* |
| `multica daemon stop` | L |

### `multica runtime`

| 命令 / 位置参数 | 类别 |
| --- | --- |
| `multica runtime activity <runtime-id>` | R |
| `multica runtime concurrency <runtime-id> <limit&#124;none>` | A |
| `multica runtime delete <runtime-id>` | D |
| `multica runtime list` | R |
| `multica runtime profile create` | A |
| `multica runtime profile delete <profile-id>` | D |
| `multica runtime profile list` | R |
| `multica runtime profile set-path <profile-id>` | L |
| `multica runtime profile unset-path <profile-id>` | L |
| `multica runtime profile update <profile-id>` | A |
| `multica runtime rename <runtime-id> <name>` | A |
| `multica runtime update <runtime-id>` | A |
| `multica runtime usage <runtime-id>` | R |

### `multica attachment`

| 命令 / 位置参数 | 类别 |
| --- | --- |
| `multica attachment download <attachment-id>` | L |
| `multica attachment upload <path>` | W |

### `multica auth`

| 命令 / 位置参数 | 类别 |
| --- | --- |
| `multica auth logout` | L |
| `multica auth status` | R* |

### `multica config`

| 命令 / 位置参数 | 类别 |
| --- | --- |
| `multica config set <key> <value>` | L |
| `multica config show` | R* |

### `multica login`

| 命令 / 位置参数 | 类别 |
| --- | --- |
| `multica login` | L |

### `multica setup`

| 命令 / 位置参数 | 类别 |
| --- | --- |
| `multica setup cloud` | L |
| `multica setup self-host` | L |

### `multica update`

| 命令 / 位置参数 | 类别 |
| --- | --- |
| `multica update` | L |

### `multica user`

| 命令 / 位置参数 | 类别 |
| --- | --- |
| `multica user profile get` | R* |
| `multica user profile update` | W |

### `multica version`

| 命令 / 位置参数 | 类别 |
| --- | --- |
| `multica version` | R |

### `multica environment`

| 命令 / 位置参数 | 类别 |
| --- | --- |
| `multica environment list` | R* |
| `multica environment start <name>` | X |
| `multica environment stop <name>` | X |

## 命令组、别名及辅助入口

下列路径均以 `multica` 打头。`setup` 无子命令时等同 `setup cloud`，会配置、认证并启动 Daemon。

- `agent`, `agent env`, `agent mcp`, `agent skills`
- `autopilot`, `chat`
- `issue`, `issue batch`, `issue comment`, `issue label`, `issue metadata`, `issue property`, `issue pull-requests`, `issue subscriber`, `issue wakeup`
- `issue-status`, `label`, `property`, `repo`
- `project`, `project member`, `project resource`, `project workflow`
- `skill`, `skill files`, `skill label`
- `squad`, `squad member`, `view`
- `workflow`, `workflow handoff`
- `workspace`, `workspace mcp`, `workspace member`
- `daemon`, `daemon autostart`, `runtime`, `runtime profile`
- `attachment`, `auth`, `config`, `setup`, `user`, `user profile`, `environment`

- 应用别名：`env` → `environment`，`issue prs` → `issue pull-requests`，`issue subissues` → `issue children`，`issue history` → `issue timeline`，`repo rm` → `repo remove`。
- `daemon probe-runtimes` 是 Desktop 本机发现辅助。已弃用的 `issue rerun` 使用当前指派，精确重跑旧 Run 使用 `issue rerun-task`。
- Cobra 辅助入口包括 `help [path...]`、`completion {bash,zsh,fish,powershell}`、隐藏的 `__complete` / `__completeNoDesc`。`__multica_execenv_prepare` 和 `__multica_cursor_hook` 仅供内部进程协议使用。[根注册与入口](https://github.com/multica-ai/multica/blob/2fcb424b72b024f65161809081009063846ea44d/server/cmd/multica/main.go)

## 与 v0.9.0 对照

- 新命令包括 `issue batch update`、`issue pull-requests link/unlink`、`project archive/restore` 和 `view create/delete/duplicate/update`。项目归档会暂停该项目的相关 Autopilot，恢复项目时须另核 Autopilot 状态。
- `workflow handoff set`、`issue-status` 和 `issue metadata` 已存在于 v0.9.0。v0.10.0 的实际配置以 `project workflow get` 和 `workflow get` 为准。对比 `--help` 核对各版本参数。
- 本版可用 `issue comment add --steer` / `--steer-active` 补充运行中任务，按实际回执确认送达。`skill create/update` 和 `skill files upsert` 可通过 UTF-8 文件或 stdin 提供内容。`issue runs --active` 聚焦在途运行，`issue run-messages --since` 按序号续读。
- [认证与调用](access.md)包含操作者与任务身份、自托管接入、状态/交接/评论副作用、原始结果及技能挂载说明。
