# Multica v0.10.0 认证、查询与操作

本页以已安装的 CLI v0.10.0 和[上游提交 `2fcb424b72b024f65161809081009063846ea44d`](https://github.com/multica-ai/multica/commit/2fcb424b72b024f65161809081009063846ea44d)为基线。操作前以目标 CLI 的 `multica version`、相关 `--help` 及服务器部署版本核对兼容性。在线文档会继续更新。

## 选择调用身份

| 身份 | 凭据来源及范围 |
| --- | --- |
| 操作者 | 在已授权的 CLI profile 中使用个人访问令牌（PAT，`mul_`）。PAT 代表真实账号并继承其访问权，操作受账号角色、对象权限及本次授权约束。浏览器会话使用其自身 Cookie 与 CSRF 流程，勿复制到脚本。 |
| Multica 智能体 Run | Daemon 注入临时 `mat_` 令牌到 Run 的 `MULTICA_TOKEN`，绑定用户、workspace、智能体和 Run，有效期最长 24 小时并在结束时清理。服务端绑定身份，不能靠设置请求头改变归属。某些端点只接受操作者身份。 |
| 运行接入 | `mcn_` 属 Multica Cloud Fleet，`mdt_` 属内部 Daemon 认证。自托管业务 CLI 使用前两种业务身份，不用内部凭据或其他服务的令牌。 |

直接 REST 使用 `Authorization: Bearer`。workspace 级路由按需传 `X-Workspace-ID`，仍需对象权限。使用已核准的目标 origin（TLS 或经确认加密的受控私网），拒绝跨 origin 重定向。在本项目仓库内，获授权的操作者工具可从私有 `.env` 读取 `MUL_TOKEN`，仅请求进程持有。发布到其他环境时使用其获准的安全凭据入口。不要把秘密写到技能、命令参数、任务内容、日志或版本库。避免原样输出 `agent env get`、`config show` 或 `--debug`，其中可能有凭据或内部配置。按[上游令牌说明](https://github.com/multica-ai/multica/blob/2fcb424b72b024f65161809081009063846ea44d/apps/docs/content/docs/auth-tokens.zh.mdx)及[服务端认证逻辑](https://github.com/multica-ai/multica/blob/2fcb424b72b024f65161809081009063846ea44d/server/internal/middleware/auth.go)核对身份。

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
- 在 Run 内用 `"$MULTICA_CLI_PATH" ...`（POSIX / Git Bash）或 `& "$env:MULTICA_CLI_PATH" ...`（PowerShell），沿用已注入的 server、workspace 和 Run 身份，不另登 PAT profile。目标权限不足时，以实际拒绝说明交给获授权的操作者办理，保留最小回执。参见[Daemon 注入的运行指引](https://github.com/multica-ai/multica/blob/2fcb424b72b024f65161809081009063846ea44d/server/internal/daemon/execenv/runtime_config_sections.go#L41-L57)。
- 经授权单独接入自托管实例时，先确认 API origin 和前端 origin。可在指定 profile 设置 `config set server_url` / `app_url`，交互执行 `multica --profile pilot login --token` 并在终端输入令牌。`setup self-host` 会配置地址、登录并启动 Daemon。其本机缺省为 API 8080、Web 3000，外部机器应使用已核准的实际地址。登录动作可启动或更新本机运行连接，先区分只读核验与新增接入。

## 最小 REST 接口

以下为 v0.10.0 [路由](https://github.com/multica-ai/multica/blob/2fcb424b72b024f65161809081009063846ea44d/server/cmd/server/router.go)下的查询候选。优先用已配置 CLI，长驻集成按需选择窄接口并投影字段。

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

`issue runs --active` 只查在途执行。`--siblings` 跨父子任务扩展并隐式启用 `--active`，最多 20 行，仅供协作排查。读取失败区分未认证、无权限、对象缺失、分页未完、协议或连接故障。未知写结果先用原对象、评论 ID 或 Run UUID 对账，避免盲重试。

## 状态、交接与评论

- 用 `issue-status list` 取得状态 key 与类别，`project workflow get <project>` 和 `workflow get <workflow>` 核对实际步骤及 handler。工作流状态 handoff 需要任务属于项目。状态发生变更并进入配置步骤时可指派 handler 并自动启动；旧状态重复提交不会重新进入。手动指定 assignee 会保留显式选择。只迁项目默认不交接；若具体请求需要让迁入执行工作流步骤，先用 `GET .../workflow-handoff?project_id=...` 预览，再按固定版 API 以 `PUT /api/issues/{id}` 提交 `project_id` 和 `enter_workflow_step: true`。参见[交接决策](https://github.com/multica-ai/multica/blob/2fcb424b72b024f65161809081009063846ea44d/server/internal/handler/issue_workflow_entry.go#L19-L115)及[更新字段](https://github.com/multica-ai/multica/blob/2fcb424b72b024f65161809081009063846ea44d/server/internal/handler/issue.go#L3791-L3812)。
- `workflow handoff set` 可按项目复制工作流后再设置 handler。`project workflow set --dry-run` 可先核状态迁移，`--map old=new` 在存在不兼容状态时显式映射。内置 handler 没有“原执行者”选项，记名退回须从候选 Run 的 `agent_id`、交付评论来源等核对原执行者，并在获授权时一次更新 assignee 与返工状态。`--back` 给步骤定义回退目的状态，不能代替对执行者的核验及必要改派。
- `issue assign/status/update --no-start` 仍会修改业务对象。若应触发执行，核对新 Run、目标 agent UUID 和真实状态。`issue metadata set --type string` 可将结构化记录存为 JSON 文本，读回后解码与校验。原生 metadata 仅支持 string、number、bool，选用 CLI 推断时注意数字样式字符串与布尔值的区别。参见[metadata 校验](https://github.com/multica-ai/multica/blob/2fcb424b72b024f65161809081009063846ea44d/server/internal/handler/issue_metadata.go#L59-L77)。
- 用 `issue comment add --content-file <UTF-8文件>` 保留多行与附件引用。评论触发的 Run 按 `--parent <触发评论ID>` 回传。纯记录时用首个空白分隔 token `/note`，该版本抑制智能体触发。普通评论可以按提及、线程及指派触发，保存评论与派发结果分开核验。`--steer <run>` 或 `--steer-active` 需要目标 Run 支持补充（`can_supplement`），回执可能实际排队、合并、延期或阻止，查 `trigger_outcomes` 和 Run，不以该 flag 推断实时送达。参见[评论触发逻辑](https://github.com/multica-ai/multica/blob/2fcb424b72b024f65161809081009063846ea44d/server/internal/handler/comment.go#L1945-L2015)。
- `issue cancel-task <run> --issue <issue>` 用原 Run 对账。取消是执行控制，已有文件或外部动作须另行核验。`issue rerun-task <run> --issue <issue>` 创建新 Run，沿原执行智能体与触发来源并可能续用会话/目录。`--fresh` 请求新会话与目录。先核自动重试及原 Run 状态，防止重复。

## 管理员挂载技能

经授权可用 `skill import --file` 导入含 `SKILL.md` 及所需 `references/` 的包。已有同名技能先核其 ID 和来源，再按需用 `skill update` 与 `skill files upsert` 更新对应文件。通过 `agent skills list` 核实当前分配，再用 `agent skills add --skill-ids <id>` 增量挂载并读回，`set` 会替换全部。配置、技能挂载与运行权限分别核验。保留现有运行时与凭据来源；首次真实执行按具体任务授权。命令见 [v0.10.0 总表](cli-v0.10.0.md)。
