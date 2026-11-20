# ADR-002　Dot 身份与跨工作区授权

**状态**　Proposed · 2026-11-20。公子确认的 G8 业务授权和岗位常设授权已有独立依据。本提案定义新 `multica-backend` MCP 如何落实这些授权。原生接口取证固定在 Multica v0.11.0 提交 `cb190810a659c1a61c4a86d9f6ecfc9df4b086d8`。[协作规范](../../skills/workspace-coordination/SKILL.md) · [Task Mailbox 联验记录](https://github.com/CF-FE/task-mailbox-mcp/blob/55217ff344021c34d227ac26fe38de61826bc3e3/docs/verification.md#2026-11-20--mac-协调桥拆卸与-multica-接手) · [Multica 发布记录](https://github.com/multica-ai/multica/releases/tag/v0.11.0)

## 决策

云端 Dot 经独立 HTTPS MCP 授权入口，以已验证的 OAuth 签发方和稳定主体绑定 G8。入口公布自己的受保护资源元数据，按 MCP HTTP 授权流程验证资源受众、有效期和作用域。服务端用已验证主体查询允许的动作和实例。G8 的常设权限覆盖 Task Mailbox 全部现有和后续项目，也覆盖本方案中所有已接入 Multica 工作区的项目业务操作。每次实际操作还需通过 MCP 动作白名单、实例接入登记和 Multica 原生权限。请求正文的角色、`sender`、账号名和身份头都不能赋权。Task Mailbox `whoami` 返回的 `all_projects` 证明信箱侧权限。[协作规范](../../skills/workspace-coordination/SKILL.md) · [MCP HTTP 授权规范](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization#token-audience-binding-and-validation)

每个接入的 Multica 实例为 Dot 登记专属账号、预期 `user_id` 和服务端秘密引用。账号由实例管理方按原生流程建档，按工作区授予业务所需的成员角色，并为私有项目和受限 Agent 办理适用的原生权限。MCP 用该账号专属 `mul_` PAT 访问固定 API origin，部署、换证及恢复时以 `GET /api/me` 读回的 `id` 比对预期账号。Multica 把写入归到这个账号，MCP 审计另记实际认证的 G8 主体。账号获得的工作区或对象权限也是该 PAT 可行使的范围，因此实例管理、成员与权限变更、秘密读取和运行环境配置由各自的原生管理入口办理。新项目按工作区动态发现，G8 的业务授权自动适用。私有项目仍须经原生项目成员资格校验，工作区 owner/admin 也受该规则和 Agent 调用范围约束。[PAT 语义](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/apps/docs/content/docs/auth-tokens.mdx#L18-L28) · [账号读回](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/handler/auth.go#L498-L517) · [成员角色边界](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/apps/docs/content/docs/members-roles.mdx#L24-L36)

协调员和项目负责人按在任岗位处理其范围内的交办、决策和回报。在 Multica Run 内使用 Daemon 注入的 `mat_`，其 `user_id`、`workspace_id`、`agent_id`、Run 由 Multica 绑定，有效期最长 24 小时，运行结束清理。显式选择另一工作区会被拒绝。账号级 `/api/me` 仍读回绑定用户，`/api/workspaces` 按绑定用户查询成员关系，两者均不能证明该 Run 可操作返回的每个工作区。Dot 对外入口只接受自己的 OAuth 令牌。上游适配器仅从受控来源取上述专属 PAT。Mike 的操作者凭据、Run 凭据、Daemon 和云节点凭据、腾讯云补报凭据、Task Mailbox 与 Decision Service 的 OAuth 状态各有持有者与用途。[令牌类型](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/apps/docs/content/docs/auth-tokens.mdx#L72-L95) · [身份绑定和请求头处理](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/middleware/auth.go#L59-L145) · [Run 工作区拒绝](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/middleware/task_token_workspace.go#L39-L45) · [工作区列表成员查询](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/pkg/db/queries/workspace.sql#L1-L8)

## 接口与岗位解析

实例登记使用稳定的 `instance_id` 和受信 API origin。按 instance、workspace、project UUID 解析对象，业务工具每次传入明确的目标范围，列表只展示调用者可用的接入范围。服务端构造请求，只发送一个受控的工作区选择器。账号路由无须工作区头，按路径挂载的工作区路由使用路径 UUID，其他工作区路由使用 `X-Workspace-ID`。实例多个时，同名工作区、项目或角色不做自动匹配。对象引用核对所属 workspace/project，Run 再核其所属 Issue。[账号与工作区路由](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/cmd/server/router.go#L1779-L1837) · [工作区选择与权限](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/middleware/workspace.go#L115-L164) · [Issue 和 Run 路由](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/cmd/server/router.go#L2184-L2229)

| 用途 | v0.11.0 原生请求与读取约束 |
| --- | --- |
| 验证 Dot 身份与工作区权限 | `GET /api/me` 取 `id`。用 `GET /api/workspaces` 取得该账号所在工作区，和已接入登记求交集。用 `GET /api/workspaces/{workspace_id}` 核对目标 UUID，需角色证据时用 `.../{workspace_id}/members` 查同 `user_id` 的 `role`，响应仅投影本次所需字段。 |
| 找现任协调员 | 启用工作区时登记 `(instance_id, workspace_id, 当前协调员的 agent_id)`，附任命来源并用 `GET /api/agents/{agent_id}` 读回原生工作区、状态和运行时绑定。对内置岗位可从 `GET /api/agents` 用 `system_key=mika` 辅助核对。当前 `cloud-work` 的登记为 Mike。其他工作区按各自任命处理。原生 `system_key=mika` 标识内置 Agent。派发前核对接入登记、原生 Agent 和目标工作区一致。 |
| 找项目与当前负责人 | `GET /api/projects` 枚举工作区中可见的项目，具体操作前用 `GET /api/projects/{project_id}` 核对 `workspace_id` 和 `lead_type/lead_id`。两者均为 null 时标记未任命，依现有协作规范交工作区协调员。`agent` 的 ID 用 Agent 详情核对。`member` 的 ID 对应工作区成员响应的 `user_id`，用成员列表核对。字段不成对、类型不受支持或对象跨工作区时挂起核任职。工作区可见项目获准换任后，可用 `PUT /api/projects/{project_id}` 同时写两个字段并读回。若项目采用 `project_lead` 工作流步骤，另核其当前生效配置和派发结果。 |
| 核对目标可执行 | 确认协调员或 Agent 负责人可被该专属账号调用、所属 Runtime 与任务匹配，私有项目中同时核实 Agent 所有者可见项目。工作机离线通过实际派发回执显示等待或阻塞。成员负责人通过原生任务交接，由本人客户端处理。 |

[项目字段与查询](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/handler/project.go#L26-L43) · [项目读取与可见性](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/handler/project.go#L278-L302) · [成员响应](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/handler/workspace.go#L568-L606) · [CLI 成员 ID 解析](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/cmd/multica/cmd_issue.go#L3684-L3692) · [更新 lead 的原生逻辑](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/handler/project.go#L753-L780) · [Agent 岗位与运行时字段](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/handler/agent.go#L53-L84) · [私有项目指派检查](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/handler/project_access.go#L185-L224) · [工作流交接](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/handler/issue_workflow_entry.go#L88-L115)

任命本身只更新项目，具体 Issue 再走原生指派或工作流。私有项目换 lead 属于访问管理，因为任命账号成员可加其入项目并转移访问管理职责，改成 Agent 或清空也可能变更访问管理人。Dot 的普通项目更新只接受工作区可见项目的 lead 变更。私有项目换任由有权的原生访问管理者办理，回读 lead 与成员资格。Agent 在私有项目内运行时，原生访问还会核 Run 发起者和 Agent 所有者。[项目负责人和私有项目规则](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/apps/docs/content/docs/projects.mdx#L66-L91) · [私有负责人访问管理校验](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/handler/project_member.go#L144-L181) · [负责人自动入组](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/handler/project_member.go#L256-L265)

新增工作区的验收由其管理方核 Dot 原生身份、目标项目权限和当地协调员。工作区接入后，新项目沿用规则，无须逐项重批 G8 的常设业务授权。协调员换任时，核实并启用新任绑定后切换登记，同时保存旧任、原 Issue、在途 Run、原 job 与验收人。已派的请求保留原接手记录，原单交接通过明确业务动作完成。已受理但尚未发出且承接人已变的写入先挂起核对。已发但无回包先按原请求对账。新任务在派发前读取现任登记，发现缺失或冲突就回报待核。[协调员登记](../harness-role-guide.md#工作区协调员-mike) · [派发合同](003-command-delivery.md)

## Skills、MCP 和 OAuth 的装配

- 工作区 owner/admin 维护共享 MCP 库，按现有常设授权给协调员及 Agent 项目负责人增量分配。用 `GET /api/workspaces/{workspace_id}/mcp-servers` 确认库条目，Agent owner 或工作区 owner/admin 用 `POST /api/agents/{agent_id}/mcp-servers` 带同工作区的 `server_id` 分配，再用同路径读取 ID 和 `enabled`。读取 `GET /api/agents/{agent_id}/skills` 核对已分配 Skill，需要补齐时用 `POST .../skills/add` 增量挂载。配置动作走原生管理面，本提案的 Dot 业务工具只读取必要证明。Workspace 库条目需绑定并启用才能进入 Run。claim 实际合并的优先级从高到低为单任务覆盖、Agent 自有配置、已启用工作区绑定。宿主还可能合并本地配置。启用或撤下绑定后，应在新 Run 验工具，检查同名覆盖和宿主继承。[管理与绑定路由](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/cmd/server/router.go#L1859-L1889) · [Agent 绑定路由](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/cmd/server/router.go#L2475-L2491) · [读回字段及写入角色](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/handler/workspace_mcp_api.go#L336-L389) · [同工作区约束](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/handler/workspace_mcp_api.go#L424-L438) · [绑定合并顺序](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/handler/workspace_mcp.go#L25-L56) · [原生宿主继承和 OAuth](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/apps/docs/content/docs/daemon-runtimes.mdx#L114-L149)
- OAuth 由实际 MCP 客户端管理。成员负责人在本人客户端接入 Decision Service，Agent 负责人在实际运行该角色的 harness/profile 核验。服务 URL 可复用。同一账号、同一 URL、同一 harness/profile 和有效登录时，依宿主规则复用登录。换任、换宿主、换身份或授权失效后按实际客户端办理。Cursor 文档明确记录其按 Agent 和运行机保存的 OAuth 状态及原地运行等例外，此机制不能外推到 OMP。配置读回后须在新 Run 或成员真实客户端核对服务实际认出的主体与目标项目权限。[客户端与宿主边界](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/apps/docs/content/docs/daemon-runtimes.mdx#L136-L149) · [当前岗位装配依据](../../skills/workspace-coordination/SKILL.md#怎样快速判断)
- 现有记录已核实 Mike 在 OMP 的 Task Mailbox 身份、原 job 读取及写回，和 CLOU-21 的 Decision Service 现有记录读回。CLOU-22 中 Mike 带项目 UUID 调用 `evaluate_decision` 返回 `forbidden_scope`，说明该身份在当时的 Decision Service 服务端缺少项目范围。通过原授权管理入口补齐项目权限后，沿原件验证同项目的新判断和反馈。`cloud-work` 原生项目负责人盘点当时为空，当前材料还没有负责人客户端或新任协调员的端到端证据。[CLOU-20 至 22 实单](../workflow-reporting.md) · [项目负责人盘点](../harness-role-guide.md#工作区协调员-mike)

## 凭据、审计和恢复

Vultr 只向该服务进程注入独立有限期 PAT。MCP OAuth、上游 PAT 和其他服务的凭据各自隔离，令牌从认证层流向指定接收端。上游 origin 由服务配置固定，链路使用 TLS 或已核验的加密私网，拒绝重定向。审计记录认证主体标识、上游账号 UUID、动作、实例与对象 UUID、稳定请求 ID、原生对象与结果阶段、安全的错误分类和时间。记录 `job_id` 仅用于原件关联。PAT、OAuth 值、任务令牌、认证头、完整配置和未脱敏请求响应均不得进入日志、回执或任务正文。轮换时发新 PAT，核同一账号和目标作用域，切换引用后在签发端撤销旧 PAT。注销 CLI 和浏览器只清理各自本地登录。凭据疑似泄露时先停对应身份的写入并在签发端吊销，再用原请求对账。[上游撤销语义](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/apps/docs/content/docs/auth-tokens.mdx#L70-L84) · [MCP 凭据与受众](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization#access-token-privilege-restriction)

| 信号 | 恢复与对外语义 |
| --- | --- |
| MCP OAuth `401` / `403` | `401` 由 HTTPS MCP 层按 OAuth 规范发起认证恢复。凭据有效但主体或作用域权限不足时用 `403`，由实际授权管理方核对。回查历史请求也按当前主体和目标访问权限核验。 |
| 上游 `401` 或账号 ID 不符 | 记为 Multica 身份故障，停止使用该实例这份凭据。由凭据持有人核实撤销、过期、配置或账号状态。换证后先核 `/api/me`、目标 workspace/project，再处理原请求。对外保留故障层级，避免把上游 `401` 转成 Dot OAuth 登录挑战。 |
| 上游 `403` | 停止该动作。按目标与原生响应核查工作区角色、任务令牌绑定、私有项目派发权限、Agent 调用权限或端点限制。恢复授权时沿原件办理，避免使用另一账号或命令路径绕过。 |
| 上游 `404` | 对调用方返回目标缺失或当前不可见，同样适用于私有项目下的对象。仅在当前身份已授权范围核对实例和 UUID。必要时由目标管理方核成员资格或迁移前后归属。已接入目标遇到不可识别的路由，交固定版本兼容检查处理。 |
| EasyTier、HTTP 超时、`5xx` | 记为链路或上游故障。恢复后核 `/health`、`/readyz`、账号和目标原生范围，查询可有界重试。对已受理的写操作先检查原生对象和 Run，回包不明时沿原稳定请求 ID 对账。Vultr MCP 停用时，获准协调员可在原生 Multica 按原件接续，先核是否已派发。 |

[工作区缺失、非成员及角色检查](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/middleware/workspace.go#L197-L260) · [私有项目隐藏语义](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/handler/project_access.go#L84-L101) · [派发对账](003-command-delivery.md) · [回程恢复](004-reporting-and-recovery.md)

## 备选、后果和验收

复用 Mike 的 PAT 可以少建一个账号，但 Multica 会把 Dot 写入归到 Mike，换任或撤销会同时影响两条链路。复用 Run token 便于协调员调用原生接口，其工作区绑定与 Run 生命周期无法覆盖跨工作区的常驻入口。每工作区都另建账号可缩小 PAT 泄露影响，代价是凭据和身份轮换数量随工作区增长。建议先采用每实例一个专属账号，以同一服务配置完成轮换和审计。若实例内出现必须分开隔离的授权域，再拆账号及对应执行身份。账号越多也不会替代私有项目 ACL 或目标范围核对。

| 验收用例 | 通过证据 |
| --- | --- |
| Dot 登录、账号归属和凭据隔离 | 新 Dot 连接走实际 OAuth 发现、授权和续登。伪造角色、错误主体/受众及其他服务令牌均在上游请求前拒绝。隔离实例读回专属账号 UUID，测试写入的原生作者和 G8 审计主体可对应。 |
| 两工作区、项目对象和私有权限 | 同一专属账号各用明确 workspace UUID 成功核读。对未登记或非成员工作区、串用项目或 Run、私有项目未入组、受限 Agent 及跨工作区 `mat_` 分别验证拒绝。已可见的私有项目从普通项目更新提交换任时，应转到访问管理流程，读回原 lead 和成员资格。注册新工作区并验证新项目可见性，无须新增业务授权代码。 |
| 换任与装配 | 试验项目分别核对空 lead、成员 lead、Agent lead。一个在途原单交接给新任并保留旧 Run 与回程。后续新单只派给新登记。验新身份实际工具与同项目 Decision 写读及反馈，同时核对旧岗位绑定或访问范围按交接移除后的行为。 |
| 错误与恢复 | 分别模拟 OAuth 失效、上游 PAT 撤销和账号不符、项目不可见、私网中断与写入后丢回包。保留正确故障层、原请求 ID 和现有回执。恢复后验证原 Issue 数、实际 Run 数与审计归属。 |

已完成公开固定源码及项目记录核对。现有记录覆盖 G8 信箱全项目权限、Mike 的原生 OMP 调用和被项目范围拒绝的案例。新 MCP 的 Dot OAuth、专属 Multica 账号、多工作区和私有权限、负责人装配、换任及断联恢复仍需隔离联验。部署与业务试点以独立授权为准。
