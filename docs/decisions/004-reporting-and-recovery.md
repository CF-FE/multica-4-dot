# ADR-004　原信箱回执与 Multica Run 补报

**状态**　Proposed · 2026-11-20（Asia/Shanghai）。本记录承接 [Dot 直连方案](001-dot-multica-gateway.md)的跨端回程设计。

## 背景与取舍

建议由 `multica-backend` MCP 提供受权交办与原件查询，协调员核对产物并负责业务回报，腾讯云现有补报器独立记录登记范围内的 Run 终态。Task Mailbox 保管原件、结果版本和读确认，Multica 保管 Issue、派发和 Run，项目指定验收人记录业务验收。沿用已获采纳的 Mac 协调桥退役和 Task Mailbox 数据库留在 win-work 的决定，以及 G8 和各岗位的既有授权。[信箱 ADR-001 局部修订](https://github.com/CF-FE/task-mailbox-mcp/blob/55217ff344021c34d227ac26fe38de61826bc3e3/docs/decisions/001-task-collaboration-platform.md) · [岗位规范](../../skills/workspace-coordination/SKILL.md)

仅靠原生通知适合内部工作，但 Worker 或协调员提前退出时，约定的跨端收件方可能缺运行证据。只靠协调员轮询信箱会频繁唤起运行时。通用自动收件虽然能降低人工交接成本，但现有信箱事件缺少可用于派发的逐件来源证明。复用直连交办与既有补报，工程成本集中在原任务关联、异常对账和登记可见性。只有出现明确的入站需求和可信来源时才启用自动接入。

## 收件与派发

| 入口 | 如何处理 |
|---|---|
| 只有信箱件 | 保存在原 `job_id` 下，等待受权操作者核读和显式交办。`list_events(cursor, limit, recipient)` 按任务最初的 `payload.recipient` 过滤整条事件链，包括回程。`sender`、`recipient`、`report_route` 和授权文本均由调用方填写。`whoami` 证明当前连接的账号，原 job/event 输出无逐件认证发件者字段。 |
| 显式交办 | 经认证的 G8 或获授权的原生操作者发出操作指令。指定工作区、项目、接手人或岗位、允许动作、验收与回程。有原 job 时核读其原件和摘要，核对目标、回程、已有 Issue 与取消标记。纯 Multica 交办在原项目回报，约定给 Dot 看的进展可用原任务引用发布观测。 |
| 可信且获准的入站 | 只有入口能独立验证来源身份，并将获准的发件者、目标工作区／项目、具体执行意图、稳定请求 ID 和内容摘要绑定到原件，才交给同一个派发入口。若不能核验则保留来件待显式处理。事件通知只可提示回查，权限和执行范围仍从受权指令取证。 |

同一交办的自动渠道和显式接手共用原关联及派发去重。原 `job_id`、摘要、实例、工作区／项目、Issue 与回程保存在交办回执和原 Issue 绑定中。重复来件按原键回查，目标、回程或摘要冲突交协调员核对。经获准的返工或重跑使用新的操作请求，保留同一业务关联和新旧 Run。一次回执缺失先查原请求、原 Issue 和 Run，再按派发 ADR 对账。接手人无响应或执行机离线时分别显示 Issue 是否存在、派发是否排队及是否实际开始。若启用自动入站并以游标续读，先持久记录本页事件的处理或待核去向，再推进对应收件范围的游标。工作区协调员按明确来件承接，日常报告留原 Issue 或原聊天线程。[信箱任务协议](https://github.com/CF-FE/task-mailbox-mcp/blob/55217ff344021c34d227ac26fe38de61826bc3e3/SPEC.md) · [信箱工具](https://github.com/CF-FE/task-mailbox-mcp/blob/55217ff344021c34d227ac26fe38de61826bc3e3/server.py#L105-L166)

取消件沿原 `job_id` 查询 `cancel_requested` 和 `CANCEL_REQUESTED`。派发前发现取消即暂停派发，原任务留给协调员办结。已派发时交现任受权操作者核对并对指定 Run 发出取消，读回原生终态。并发时保留实际观察到的先后和终态，已完成的 Run 仍记为 `completed`。保留历史结果、ACK 和已发观测，取消请求、原生停止与业务处置分别记录。手工接手、掉线恢复和重跑也走同一核对路径。

## 结果、读确认与验收

| 阶段 | 权威来源与可核对证据 |
|---|---|
| 运行事实 | Multica 原生 Issue 和 Run。报告完整 UUID、原生状态、发生时间与核读时间，未知发生时间保留空值。协调员或 Dot 核读 `completed` 对应的产物。交付物未核到时显示「交付待核」，保留错误或产物的受权引用。 |
| 业务回报持久化 | 协调员核对后沿原 `job_id` 以稳定 `event_id` 调 `publish_result`，保存实际 Run、交付物或失败证据、后续动作及验收人。超时先回查原事件、版本和摘要，需补传时复用原事件和原内容。实质更新沿原 job 提交新版本。只有观测约定时用 `publish_observation_batch`，标注协调员自报。 |
| 原收件人读确认 | 原 Dot 从交办回执获得 `job_id`，显式 `get_result(job_id, version)`，核读正文及 SHA-256 后调 `ack_result_read(job_id, event_id, version, result_hash)`，并以匹配的 `RESULT_READ_ACKNOWLEDGED` 事件对账。历史 ACK 事件只保存版本与摘要，真实 Dot 收件验收还需其原生会话证据。只看 `recipient=cloud-dot` 会漏掉发给协调员的 job 的全部回程事件。自动通知需要验证实际送达时间及 Dot 主动读回。 |
| 项目验收 | 指定验收人在原项目记录对应 Issue、Run、产物版本与业务结论。仅在委托或生效工作流要求独立复审时转入 `in_review`。聚合查询分别显示原生运行、已回报、信箱持久化、已读与业务验收，缺证据的维度保留未知。 |

信箱读写沿既有 OAuth 和工具合同。MCP 可在分别获准读取各来源时展示引用、状态和检查时间；来源不可用或无权读取时附原因。Decision Service 提供获准的有限选项建议，Hindsight 提供历史证据检索，GitHub Projects 按已有正式关联显示验收看板。原生项目和原件仍各自持有正式记录。[结果与 ACK 实现](https://github.com/CF-FE/task-mailbox-mcp/blob/55217ff344021c34d227ac26fe38de61826bc3e3/mailbox_store.py#L304-L375) · [汇报实例](../workflow-reporting.md#2026-11-20-实施核对)

## 新增与重跑的 Run 如何进入补报范围

1. **发现待登记项。** 只对约定跨端回报的原任务查已核验的 Issue 和原生可见 Run。创建、派发、重跑或工作流交接后读回实际 Run UUID。若派发时尚无 UUID，在对应交办回执记录「待 Run」。对在途回报事项做有界回查，涵盖工作流或经授权手工产生的新 Run，避免 Issue 状态不变时漏掉重跑。逐次核对其所属工作区、项目、Issue 与本次授权范围。意外启动的 Run 留作异常证据，未经核对的关联进入待处理列表。[固定版 Run 历史查询](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/handler/daemon.go#L6420-L6585)
2. **沿用双登记。** 现行试点的投影按 `run_reporter.registrations(issue_id, run_id)` 过滤，补报器只枚举私有配置的 `watches`。协调员从同一原件提出登记。沿现有运维权限由数据库所有者登记前者、补报服务所有者核对并更新后者。补报条目携带独立核对的信箱项目和 `task_id`，有原委托时再带 `job_id`。CLOU-20 的原任务标识碰巧等于 Issue UUID，CLOU-21 指向原协作规范任务，因此两侧 ID 要按原绑定保存。核对登记配置与实际服务身份 GET 返回的精确 Run 后才显示「已覆盖」。只完成一侧、读取不确认或出试点授权范围时分别显示「待补登记」「覆盖待核」或「未接入」，标明处理人和下次复查。每个新 Run 单独登记，保留旧 Run 和既有回执。运行身份继续只读受限视图并只向获准的信箱项目写原生观测，MCP 和协调员沿原运维交接取得登记证据。[登记与撤销](../tencent-run-reporter.md#登记撤销与升级) · [数据库投影](../../deployment/run-reader/projection.sql)
3. **复用独立 timer 与投递台账。** `multica-run-reporter.timer` 在前一轮结束约一分钟后再次触发；它可在 Agent、MCP 或 Worker 离线时处理已登记事项。补报器对 `failed`、`cancelled`、`completed` 保存完整观测、稳定事件／批次 ID，再用同源身份查原批次；只有信箱返回明确缺批次才 POST 冻结报文。匹配 `persisted: true`、来源、批次和事件集合后保存回执。超时、权限失败和非预期响应保留待发，明确的 `OBSERVATION_CONFLICT` 隔离交协调员核对。原生查询不通时保留观测时间及不可用状态，已入队的观测可单独补传。迁移或升级按现有维护手册停 timer、保存 SQLite 及登记、对照目标版本投影与原生 API，再恢复并查原批次。Vultr 入口停用时原生流程仍可接手，先核原件是否已建卡或启动。[补报实现](../../reporter/run_reporter.py) · [timer](../../deployment/multica-run-reporter.timer)

查询与报表按工作区、项目、Issue 和 Run 提供覆盖状态、最后核对时间和证据链接。对约定跨端回报的范围，列出待 Run、待登记／未接入、终态待投递、已持久化、冲突及来源不可用；业务结果、Dot 已读、项目验收单列。来源视图无记录时，结合正式 API 和两处登记核验，缺任一证据显示待核。覆盖统计以已核定的应回报 Run 为分母，来源或范围不全时展示已知范围。该视图可由原生查询、已有回执、登记核对及信箱观测组合得到。

## 证据与验收

2026-11-20 的原信箱只读复核记录如下。两个游标属于独立的信箱事件流和来源观测流。

| 对象 | 实际证据 |
|---|---|
| CLOU-20 | `multica-mike-dot-20261120-01` 的收件字段为 `cloud-dot`。首轮 OMP 缺信箱 OAuth，补齐后在原卡用新 Run 得到 v1。`get_result(..., 1)` 的 SHA-256 与游标 26 的报告及游标 27 的 ACK 相同。原 G8 在验收提示后对正文做了实际复述并签收。另有首轮 Run `01a1f707-2114-79b6-807a-16702268b29a` 的 `completed` 原生观测，信箱观测游标 278，14:09 自然周期沿用原回执。 |
| CLOU-21 | `g8-to-workspace-coordinator-20261120-01` 的收件字段为 `multica-workspace-coordinator`。G8 投件后，获授权操作者将其绑定原卡并交 Mike。游标 29 与独立 `get_result(..., 1)` 读回一致。按 `recipient=cloud-dot` 只查到 CLOU-20；按协调员收件字段能看到本件投件和 v1。当前事件流未见本件原 G8 的精确 ACK。Mike 转入 `in_review` 意外触发额外复审，复核方在额外 Run 派发前取消，原 Mike Run 已完成。 |

[现场记录](../workflow-reporting.md#2026-11-20-实施核对) · [信箱验证记录](https://github.com/CF-FE/task-mailbox-mcp/blob/55217ff344021c34d227ac26fe38de61826bc3e3/docs/verification.md) · [独立补报试点](../tencent-run-reporter.md#本轮试点与实测)

| 开发验收场景 | 可观察的通过条件 |
|---|---|
| 收件、派发与回程 | 旧信箱仅存来件。G8 显式交办同一件，读到唯一原 Issue 和预期 Run；授权可信入站若启用，对重复投件、重放和并发显式接手仍返回同一绑定。源身份仅自称、目标越界或摘要冲突时零派发。协调员回原 job，原 G8 核读 v1 并写匹配 ACK，项目验收可独立查询。仅回报委托产生零额外复审 Run。 |
| 离线、重复与取消 | 模拟建卡后丢失响应、入口重启和 Worker 离线，能以原请求对账且零额外派发；未知路径显示待核与接手人。提交取消前后的状态、停机证据及取消与完成竞争的实际结果可区分，原业务回执仍可查询。错误版本／摘要的 ACK 被拒绝，重复提交同一精确 ACK 读回原事件。 |
| 独立补报、新 Run 与部分登记 | 对约定回报的任务触发新 Run 和同卡重跑，分别显示待登记直至两处登记及读取已核，旧 Run 仍可查。测试另一侧缺登记、范围不符或源不可用时有诊断且零误发；在 Worker 和协调员均未回报的隔离失败场景，timer 产生一条带该 Run 引用的失败观测，结果栏继续待核。 |
| 补报丢响应、重启与回退 | 服务端已入库后断开，发送端重启后以原批次取回相同回执，仍只有一条观测且不多开 Run。信箱不可用时原生工作继续，原件待补。伪 404、协议错误或冲突保留原件并显示相应状态，其他登记可继续。关停新 MCP 写入后，协调员能从原生入口按原件接手。 |

既有读取与补报模块的 14 项本地回归已通过，包含精确匹配、范围拒绝、超时、重启和去重。线上已证明一笔 `completed` 观测、一次自然周期续跑和 CLOU-20 原 Dot 精确签收。新 MCP 从云端独立建卡、可信入站、CLOU-21 的原 G8 精确签收、Dot 自动唤醒、线上失败终态及新增或重跑的完整覆盖链仍待各自验证。[读取测试](../../tests/test_run_reader.py) · [投递测试](../../tests/test_run_reporter.py)
