# Multica 认证、查询与操作

腾讯云当前部署为 v0.13.0。操作前核对目标 CLI 的 `multica version`、相关 `--help`、实际身份及服务端版本。下文的固定源码链接随各条规则保留其取证版本。[v0.13.0 CLI 差异与验证](cli-v0.13.0.md) · [v0.12.1 历史实测](cli-v0.12.1.md)

## 选择调用身份

| 身份 | 凭据来源及范围 |
| --- | --- |
| 操作者 | 在已授权的 CLI profile 中使用个人访问令牌（PAT，`mul_`）。PAT 代表真实账号并继承其访问权，操作受账号角色、对象权限及本次授权约束。浏览器会话使用其自身 Cookie 与 CSRF 流程，勿复制到脚本。 |
| Multica 智能体 Run | Daemon 注入临时 `mat_` 令牌到 Run 的 `MULTICA_TOKEN`，绑定用户、workspace、智能体和 Run，有效期最长 24 小时并在结束时清理。服务端绑定身份，不能靠设置请求头改变归属。某些端点只接受操作者身份。 |
| 运行接入 | `mcn_` 属 Multica Cloud Fleet，`mdt_` 属内部 Daemon 认证。自托管业务 CLI 使用前两种业务身份，不用内部凭据或其他服务的令牌。 |

直接 REST 使用 `Authorization: Bearer`。workspace 级路由按需传 `X-Workspace-ID`，仍需对象权限。使用已核准的目标 origin（TLS 或经确认加密的受控私网），拒绝跨 origin 重定向。在本项目仓库内，获授权的操作者工具可从私有 `.env` 读取 `MUL_TOKEN`，仅请求进程持有。发布到其他环境时使用其获准的安全凭据入口。不要把秘密写到技能、命令参数、任务内容、日志或版本库。避免原样输出 `agent env get`、`config show` 或 `--debug`，其中可能有凭据或内部配置。[上游令牌说明](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/apps/docs/content/docs/auth-tokens.zh.mdx) · [服务端认证逻辑](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/middleware/auth.go)

## CLI 查询与自托管接入

已配置的 `pilot` profile 示例，`WS_ID`、`ISSUE`、`RUN_ID` 为目标标识：

```bash
multica version
multica --profile pilot auth status
multica --profile pilot workspace list --output json
multica --profile pilot --workspace-id "$WS_ID" issue get "$ISSUE" --output json
multica --profile pilot --workspace-id "$WS_ID" issue runs "$ISSUE" --output json
multica --profile pilot --workspace-id "$WS_ID" runtime list --output json
```

- `auth status` 可能在未登录或凭据过期时返回退出码 0。用 `GET /api/me` 或获准的目标 workspace 查询验证实际身份和范围。CLI 业务查询无需启动本机 Daemon。
- 在 Run 内用 `"$MULTICA_CLI_PATH" ...`（POSIX / Git Bash）或 `& "$env:MULTICA_CLI_PATH" ...`（PowerShell），沿用已注入的 server、workspace 和 Run 身份，不另登 PAT profile。目标权限不足时，以实际拒绝说明交给获授权的操作者办理，保留最小回执。[Daemon 注入的运行指引](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/daemon/execenv/runtime_config_sections.go#L43-L58)
- 经授权单独接入自托管实例时，先确认 API origin 和前端 origin。可在指定 profile 设置 `config set server_url` / `app_url`，交互执行 `multica --profile pilot login --token` 并在终端输入令牌。`setup self-host` 会配置地址、登录并启动 Daemon。其本机缺省为 API 8080、Web 3000，外部机器应使用已核准的实际地址。登录动作可启动或更新本机运行连接，先区分只读核验与新增接入。

## Daemon 重启与原卡验证

- 重启前用 `daemon status --output json` 核对目标 profile、Daemon ID、进程版本以及 `active_task_count`、`running_task_count`、`resource_wait_task_count`。按 Daemon ID 核对服务端运行时的在途 Run，覆盖关联工作区。等待目录的 Run 仍属在途。计数字段缺失时按服务端记录或本机日志补证。把最后一次空闲检查放在获准的 `daemon restart` 前。
- 重启后用 `daemon status --output json` 核对 `cli_version`、新进程及工作区。用该工作区的 `runtime list --output json` 按同一 Daemon ID 核对原 runtime ID、`online` 和重启后的 `last_seen_at`。[Daemon 官方说明](https://multica.ai/docs/daemon-runtimes)
- 有实际领单验收授权时，先确认已有验证卡、目标 Agent 绑定的 runtime ID 和卡上在途 Run。核对工作流和指派后发一条定向触发评论，沿用原卡状态与归属。可以让目标 Run 执行系统信息查询及对一次性字符串计算 SHA-256，由操作者独立比对输出。
- 用 `issue runs <issue> --output json` 按 `trigger_comment_id` 找本次 Run，核对新增 Run 数量、目标 `runtime_id`、开始和终态。用 `issue run-messages <run> --issue <issue>` 核对工具执行及真实输出，用 `issue comment list <issue> --output json` 按 `parent_id`、评论作者和正文核对回件。CLOU-24 实测覆盖 mac-work v0.12.1 Daemon 在腾讯云 v0.11.0 上的领取、执行和原卡回传。

只读任务的回传直接用内存文本，单行可用 `--content`，多行可由 stdin 传入。在评论触发的 Run 中，`TRIGGER_COMMENT_ID` 取该 Run 的原触发评论，`OBSERVED_RESULT` 取实际工具输出。经授权后，将静默回执直接传给原卡。

```bash
printf '/note\n\n%s\n' "$OBSERVED_RESULT" |
  "$MULTICA_CLI_PATH" issue comment add "$ISSUE_ID" \
    --parent "$TRIGGER_COMMENT_ID" --content-stdin --output json
```

## 收件箱与会话唤醒

- `inbox list --output json` 读取当前身份在目标 workspace 的活跃通知，保留已读状态。`--project` 接受项目 UUID 或唯一 ID 前缀，和 `--type` 都是客户端筛选。Run 使用注入的任务令牌时，服务端要求经验证的上游发起人与运行时所有者为同一人。其他来源的 Run 或云节点凭据会被拒绝。仅引用任务需要的通知字段。[CLI 查询](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/cmd/multica/cmd_inbox.go#L50-L95) · [服务端权限检查](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/handler/inbox.go#L219-L313)
- `chat wakeup` 使用当前会话 Run 的任务令牌，服务端从 Run 确定会话。Issue 内的唤醒使用 `issue wakeup`。获授权需要回到同一会话报告时，`chat wakeup create` 提供标题、唤醒指令和一种触发方式。可按一个条件（如 `--until-run <Run UUID>`）、一次定时（`--at` 或 `--after`）或限期检查（`--every`）触发。一次性提醒最远可设到 30 天后。每个会话最多 10 个活跃唤醒，同一 workspace 内每位请求人最多 50 个。条件与检查默认 24 小时到期，最长 7 天。`--every` 间隔至少 10 分钟，单个唤醒最多检查 100 次。触发后回到原会话及其 IM 线程（若有）。`--until-run` 响应完成、失败或取消，回报前核对原 Run 终态和产物。[CLI 参数](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/cmd/multica/cmd_chat_wakeup.go#L19-L71) · [会话绑定](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/handler/chat_wakeup.go#L95-L127) · [期限校验](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/service/chat_wakeup.go#L103-L179) · [数量校验](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/service/chat_wakeup.go#L284-L293)
- 创建后用 `chat wakeup list` 或 `chat wakeup get <id>` 核对条件、状态和截止时间。`update <id>` 会替换配置并重算相对期限。在 `--every` 触发的检查轮次里，用 `checkin <id> --note <观察结果>` 静默结束本轮并继续等待。目标达成用 `finish <id>` 结束后续检查。到期的最后一轮直接回报进展。[会话唤醒操作](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/service/chat_wakeup.go#L425-L487)

## 最小 REST 接口

优先用已配置 CLI，长驻集成按需选择窄接口并投影字段。[v0.13.0 服务端路由](https://github.com/multica-ai/multica/blob/35b54a3742bb51bdf5ffa688655367ec98044862/server/cmd/server/router.go)

| 请求 | 用途与证据边界 |
| --- | --- |
| `GET /health`、`GET /readyz` | 区分连通与 DB/迁移就绪，随后再核调用身份。 |
| `GET /api/me` | 核对实际操作者身份，输出必需字段。 |
| `GET /api/issues`、`GET /api/issues/{id}` | 用目标 workspace、项目、对象 ID 和有界分页查询。CLI `issue list --fields` 在客户端投影，不减少服务端返回内容。 |
| `GET /api/issues/{id}/task-runs`、`GET /api/issues/{id}/active-task` | 用完整 Run UUID 匹配同一 Issue 的执行记录。active 空值仅说明该查询未返回活跃 Run。 |
| `GET /api/tasks/{taskId}/messages` | 读取指定执行的原始消息。先核 Run 归属，按需投影工具结果。CLI 支持 `issue run-messages "$RUN_ID" --issue "$ISSUE" --since N --output json`，`--since` 用序号续读。 |
| `GET /api/issues/{id}/comments`、`/timeline`、`/attachments` | 核对评论来源、状态变更轨迹与附件。工具结果或附件能支持对应验收项，状态值只能证明平台结果。 |
| `GET /api/issues/{id}/metadata` | 核对所需键与值，受控流程也可用 `issue metadata get` 查询单键。 |
| `GET /api/issues/{id}/workflow-handoff` | 预览状态交接或指定 `project_id` 的项目迁入。预览表示计划，不表示已启动运行。 |
| `GET /api/inbox` | 读取当前身份的活跃通知，遵循上文的 Run 权限。 |
| `GET /api/chat/wakeups` | 用会话 Run 的任务令牌查询该会话的唤醒记录。 |

`issue runs --active` 只查在途执行。`--siblings` 跨父子任务扩展并隐式启用 `--active`，最多 20 行，仅供协作排查。读取失败区分未认证、无权限、对象缺失、分页未完、协议或连接故障。未知写结果先用原对象、评论 ID 或 Run UUID 对账，避免盲重试。

## 状态、交接与评论

- v0.13.0 操作阻塞关系前，读回未完成的阻塞项并核对解阻后的执行对象。Squad 交接先读回 `handoff_mode` 和成员角色。自动续跑与直接点名的边界见 [v0.13.0 CLI 差异](cli-v0.13.0.md)。
- 用 `issue-status list` 取得状态 key 与类别，`project workflow get <project>` 和 `workflow get <workflow>` 核对实际步骤及 handler。工作流状态 handoff 需要任务属于项目。状态发生变更并进入配置步骤时可指派 handler 并自动启动。重复提交当前状态不会重新进入。手动指定 assignee 会保留显式选择。只迁项目默认不交接。若具体请求需要让迁入执行工作流步骤，先用 `GET .../workflow-handoff?project_id=...` 预览，再按固定版 API 以 `PUT /api/issues/{id}` 提交 `project_id` 和 `enter_workflow_step: true`。[交接决策](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/handler/issue_workflow_entry.go#L19-L115) · [更新字段](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/handler/issue.go#L3790-L3809)
- `workflow handoff set` 可按项目复制工作流后再设置 handler。`project workflow set --dry-run` 可先核状态迁移，`--map old=new` 在存在不兼容状态时显式映射。内置 handler 没有“原执行者”选项，记名退回须从候选 Run 的 `agent_id`、交付评论来源等核对原执行者，并在获授权时一次更新 assignee 与返工状态。`--back` 给步骤定义回退目的状态，不能代替对执行者的核验及必要改派。
- `issue assign/status/update --no-start` 仍会修改业务对象。需要触发执行时，检查响应的 `run_outcome` 中的 `status` 和 `reason_code`，`target_id` 对应指派对象，指派给 Squad 时为 Squad ID。回执仅随原写入响应返回。v0.11.0 单条指派、状态及修改命令会把合并、延期或阻止等未启动原因写到 stderr，`issue batch update` 表格逐条显示原因。写入没有派发决策、调用者无权调用指派对象或服务端版本较旧时，响应可能省略 `run_outcome`。缺少回执时将派发结果记为待确认，在权限范围内查同一 Issue 的 Run 核对实际执行对象和状态，避免重复派发。[CLI 回执处理](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/cmd/multica/cmd_issue_run_outcome.go) · [服务端派发回执](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/handler/issue_trigger.go#L101-L144)
- `issue metadata set --type string` 可将结构化记录存为 JSON 文本，读回后解码与校验。原生 metadata 仅支持 string、number、bool，选用 CLI 推断时注意数字样式字符串与布尔值的区别。[metadata 校验](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/handler/issue_metadata.go#L59-L77)
- 用 `issue comment add --content-stdin` 保留多行正文，已有文件可用 `--content-file <UTF-8文件>`。评论触发的 Run 按 `--parent <触发评论ID>` 回传。纯记录时用首个空白分隔 token `/note` 抑制智能体触发。普通评论可以按提及、线程及指派触发，分别核验保存评论与派发结果。`--steer <run>` 或 `--steer-active` 需要目标 Run 支持补充（`can_supplement`），`trigger_outcomes` 中的 `steered` 表示评论已绑定到目标 Run。读回该评论的 `supplements[]`，按 `task_id` 核对 `status`、`delivered_at` 和 `failure_reason`。绑定失败时可能走普通派发，应同时核查同一 Issue 是否产生后续 Run。[评论触发逻辑](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/handler/comment.go#L1975-L2014) · [逐 Run 投递回执](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/handler/task_supplement.go#L100-L146) · [绑定和回退](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/handler/task_supplement.go#L223-L250)
- `issue cancel-task <run> --issue <issue>` 用原 Run 对账。取消是执行控制，已有文件或外部动作须另行核验。`issue rerun-task <run> --issue <issue>` 创建新 Run，沿原执行智能体与触发来源并可能续用会话/目录。`--fresh` 请求新会话与目录。先核自动重试、原 Run 状态及同一 Issue、同一智能体和同一评论线程的待执行队列。重跑可能取消该线程尚未开始的待执行项。已有 `running` 或 `waiting_local_directory` 的同 Issue、同智能体 Run 会继续执行，重跑在其后排队。[服务端重跑排队](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/service/task.go#L6263-L6292)

## 管理员挂载技能

1. 同步已有 Skill 时先用 `skill get <id> --with-content` 读回目标工作区、原 Skill ID、正文、文件内容和 revision，并核对既有 Agent 挂载。发现线上有独立修改时，先按原版本对照并合并。
2. 先用 `skill files upsert <id> --path <path> --content-file <file> --base-revision <revision>` 更新新增或变更的引用文件，再用 `skill update <id> --content-file <SKILL.md> --base-revision <revision>` 更新正文。每次写入使用刚读回的 revision。遇冲突或响应不明时，先读回线上状态再继续。
3. 同一 Skill ID 下读回 `metadata.version`、正文及所需引用文件，逐一对照仓库。用 `agent skills list <agent-id>` 核对原挂载及启用状态，分别记录仓库版本与平台回执。

首次新增经授权可用 `skill import --file` 导入含 `SKILL.md` 及所需 `references/` 的包。新增挂载时用 `agent skills add --skill-ids <id>` 并读回，`set` 会替换全部。配置、技能挂载与运行权限分别核验。首次真实执行按具体任务授权。[CLI 命令总表](cli-v0.11.0.md)
