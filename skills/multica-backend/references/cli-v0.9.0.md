# Multica CLI 命令总表（上游 v0.9.0）

> 用途：为 multica-4-dot 后续 MCP 选型和白名单设计提供完整命令树。**列出不是开放，也不代表本项目已经实现、已经获权或已接上实例。**

## 版本与审计边界

- 上游 [v0.9.0 发布](https://github.com/multica-ai/multica/releases/tag/v0.9.0)，[完整源码提交 `8cd8a2db978d532d8627c78cd29f05deab6c6f17`](https://github.com/multica-ai/multica/commit/8cd8a2db978d532d8627c78cd29f05deab6c6f17)。Linux/amd64 官方发布归档 SHA-256 为 `f9689733e715d07e16339ea26bf2c6ee9211c0a4934633ba91a3998f31a8798f`，与 [官方资产页](https://github.com/multica-ai/multica/releases/expanded_assets/v0.9.0) 一致；二进制报告 `0.9.0 (commit: 8cd8a2db9, built: 2026-11-13T09:37:37Z)`。
- 在临时 HOME、空进程环境、私有 Linux 用户/网络命名空间内递归抓取 `--help`；服务器变量指向本地不可用端口。然后对照 [该版本 CLI 源码](https://github.com/multica-ai/multica/tree/8cd8a2db978d532d8627c78cd29f05deab6c6f17/server/cmd/multica) 的根注册、子树注册、隐藏项、别名和无子命令分支。**未向实际实例认证、未发命令请求、未验证各功能的服务端权限/效果，也未安装至用户环境。**
- 计数：**198 个叶子入口**（根帮助递归 193 个、根分组遗漏 `environment` 的 3 个、源码隐藏 2 个）；**43 个命令组**（不计根，其中 `setup` 本身也能执行），另有 Cobra 帮助/补全及两个内部进程入口。别名、同义标志和 shell 补全不重复计数。Linux/amd64 二进制是实测范围；Windows/macOS 的本机依赖和执行语义仍需在其平台验证。
- 在线 [CLI docs](https://multica.ai/docs/cli) 并不固定到发布版；截至本次观察，在线已有 `issue batch update`、`project archive/restore`、`issue pull-requests link/unlink`，**不在 v0.9.0 注册树中**。v0.9.0 可参照 [版本固定指南](https://github.com/multica-ai/multica/blob/8cd8a2db978d532d8627c78cd29f05deab6c6f17/CLI_AND_DAEMON.md) 和实际安装二进制的 `--help`。命令存在不表示配置已开、服务器版本相容、写入获权或结果验收。

## 风险分类（按可能副作用，而非 HTTP 方法）

| 标记 | 含义 |
| --- | --- |
| R | 查询候选：仍需 workspace / 对象范围、字段投影、分页和权限验证 |
| R* | 敏感/本机读：可能返回秘密、聊天、完整轨迹、成员信息、主机路径，或依赖本机/Agent 上下文，首期不作通用 MCP |
| W | 业务写入或上传，可产生业务变化、外部数据传输或自动化事件 |
| X | 可能启动、停止、干预执行，或设置未来触发条件（可能兼具 W/A/L） |
| A | 权限、接入、运行配置或组织级管理写入 |
| D | 删除、撤销或有较大破坏面的写入；是否永久与恢复路径须按具体操作单独核对 |
| L | 本机或账号操作，可能写文件、换凭据、启动本机服务；不开放为远程通用 MCP |

表中仅列位置参数和命令路径，不穷举每个 flag。相同行前缀即命令组；`[flags]` 表示以对应版本帮助为准。

## 应用命令（逐叶列出）

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
| `multica view get <view>` | R |
| `multica view issues <view>` | R |
| `multica view list` | R |

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

## 命令组（包括非叶子节点）

下列完整路径均以 `multica` 打头。没有子命令时，通常只显示帮助；**`setup` 是实际可执行入口**，相当于 `setup cloud`，会配置云端地址、认证并启动 Daemon，不要误跑。


- `agent`, `agent env`, `agent mcp`, `agent skills`
- `autopilot`
- `chat`
- `issue`, `issue comment`, `issue label`, `issue metadata`, `issue property`, `issue subscriber`, `issue wakeup`
- `issue-status`
- `label`
- `project`, `project member`, `project resource`, `project workflow`
- `property`
- `repo`
- `skill`, `skill files`, `skill label`
- `squad`, `squad member`
- `view`
- `workflow`, `workflow handoff`
- `workspace`, `workspace mcp`, `workspace member`
- `daemon`, `daemon autostart`
- `runtime`, `runtime profile`
- `attachment`
- `auth`
- `config`
- `setup`
- `user`, `user profile`
- `environment`

## 别名、框架入口和内部入口

- 应用别名（源码五个命令节点）：`env` → `environment`；`issue prs` → `issue pull-requests`；`issue subissues` → `issue children`；`issue history` → `issue timeline`；`repo rm` → `repo remove`。
- 隐藏应用叶子已计入上表：`daemon probe-runtimes` 是 Desktop 本机发现辅助；`issue rerun <id>` 已弃用，按 **当前指派**重排一次，不是依据指定旧 Run 重跑。新集成不要开放任何一个。
- Cobra 框架入口另列：`help [path...]`、`completion {bash,zsh,fish,powershell}`、隐藏 `__complete` / `__completeNoDesc`；根 `-h/--help`、`-v/--version` 是标志，不另计应用叶子。自定义根帮助不显示 `completion` 或 `help`。
- [main.go](https://github.com/multica-ai/multica/blob/8cd8a2db978d532d8627c78cd29f05deab6c6f17/server/cmd/multica/main.go) 在 Cobra 前处理 `__multica_execenv_prepare` 与 `__multica_cursor_hook`，为进程协议而非用户 API；仅据源码识别，不执行、不封装。

## MCP 建议与已知边界

1. 第一批只考虑 `workspace list`、`project list/get`、`issue list/get`、`issue runs --full-id`、`runtime list` 等投影后的业务查询。固定服务端地址、workspace 和命令模板；Filter 型命令只接受结构化 ID、经过检查的分页参数；不暴露通用 shell、任意参数、任意 URL 或凭据输出。
2. 对 `issue run-messages`、`chat *`、`issue comment list` 默认只给必要摘要而非全量文本；不提供 `agent env get`（可返回 custom_env 明文并有审计记录）、`autopilot get --show-secrets`、全量主机日志或 `--debug` 输出。环境认证状态的 exit code 不可单独使用，源代码对 token 不存在、无效或过期也可能返回 0。
3. `issue assign/status/update --no-start` 仍是写操作；普通评论可能唤醒 Agent 或介入现有 Run，记录型评论以 `/note` 为候选并在沙箱验证。取消要回读 Run；不会撤销已产生的文件、评论或外部副作用。重跑是新 Run，默认保留原 Agent/触发上下文并尝试续用目录/会话，`--fresh` 则从新目录和会话开始。优先核对当前 Run/自动重试链和原任务映射，不凭超时盲重跑。参考 [Run 手动重试](https://multica.ai/docs/tasks#manual-retry)。
4. 直连 HTTP 时，官方认证示例有无 workspace 的 `GET /api/me` 和带 `X-Workspace-ID` 的 `GET /api/issues`；业务 API 以项目隔离的 PAT 或任务凭据访问，PAT 继承账号权限，和插件 `/v1` 专用凭据不是一回事。MCP 选型前先跑 `/health` / `/readyz`，再做隔离实例只读冒烟，不把联通当作身份授权。参考 [Multica token 文档](https://multica.ai/docs/auth-tokens)。
5. 后续每个 MCP 工具单独做：版本一致性、身份/越权拒绝、输入/分页/脱敏、未知结果对账、可逆与不可逆副作用测试。权限管理、外网通讯、触发执行、删除/本机运维不能因为 CLI 支持而批量开放。部署、凭据、事件订阅的授权独立于本目录。

