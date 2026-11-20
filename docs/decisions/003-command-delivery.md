# ADR-003　Multica 指令派发与对账

**状态** Proposed  
**日期** 2026-11-20

## 背景

交办链路需要在并发、超时和重启后找回同一张 Issue，并独立核对是否触发了预期 Run。Issue、工作流和 Run 由 Multica 持有。原信箱任务、结果版本与读确认沿用 Task Mailbox。CLOU-21 曾在回报原件时转入 `in_review`，额外触发项目复审。[实单记录](../workflow-reporting.md) · [跨端回程](004-reporting-and-recovery.md)

## 决策提案

MCP 每次受理一个权限、目标和副作用均明确的动作。首条离线路径支持建卡并交给现任协调员，或读回已有原单。实例从固定配置选择。工作区、协调员、项目及工作流从该实例的原生数据核对。`cloud-work` 可用原生 `system_key=mika` 定位岗位，再核实际 Agent UUID 和调用权限。换任导致冻结指令过期时交原责任人处理。[身份与工作区](002-identity-and-workspaces.md) · [岗位登记](../harness-role-guide.md#工作区协调员-mike) · [Agent 原生字段](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/handler/agent.go#L72-L86) · [项目读取](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/handler/project.go#L278-L317)

1. 接入层核当前身份、授权及对象，再按 `(认证主体, request_id)` 持久受理。首次交办时固定请求 ID。业务哈希覆盖实例标识、工作区、项目、协调员、原 Issue 或建卡字段，以及已有的信箱项目与 job 引用。UUID、标题和状态键规范化，描述原样保存。变更任一冻结值返回 `RequestConflict`。不同实例的原生 UUID 可能因备份恢复而重叠。适配器用实际连接的实例标识构造证据，账本核对实例、工作区和项目。
2. 指定原 Issue 时精确读回，核对归属与原件绑定。读不到或证据不符即中止。建卡前也按原生关联查重。已查到唯一匹配的原单时返回它的引用。补录关联、留言或重新指派原单各有独立的动作和授权。
3. SQLite 先持久保存 `accepted` 与冻结指令。发送前重新核授权、协调员、项目和工作流，再用条件更新将 `accepted` 认领为 `unknown`。认领提交后，只有赢家可尝试一次原生写入。网络调用在事务外执行。适配器禁用自动重试。
4. 读回可核验的 Issue 后记 `confirmed`，保留请求指纹、对象引用与原生关联键，逻辑移除冻结指令。传输、证据校验或本地最终提交出错时，调用层记录脱敏原因并按原键查询最后持久状态。

| 持久状态 | 重启后可执行的操作 |
|---|---|
| `accepted` | 进程尚未认领。服务按主体和原键取回冻结命令，重新核验授权与路由后可继续，无需来件重新附正文。 |
| `unknown` | 已认领，可能有在途请求，含认领后、网络发出前的崩溃窗口。只读对账。空结果、无权限、分页不全或多条匹配时保持待核。取得原请求已明确结束且不会继续生效的证据后，由原责任人决定是否发起新操作。 |
| `confirmed` | 已核验原生 Issue。重复返回历史收据，在当前权限范围内另查实时 Issue、Run 与结果。 |

信箱显式接手和获准入站若要共用去重，须从已验证来源域、原信箱项目、job ID、动作及受信指令修订确定同一个业务键，再映射到同一受权派发主体和稳定请求 ID。两个入口各自核授权。若必须使用不同派发主体，则指定一个写入者，其他入口回查原件。仅有相同 job 文本或相同显示名不足以建立跨渠道去重。[信箱来件约定](004-reporting-and-recovery.md#收件与派发)

## v0.11.0 原生关联

- 在试点工作区使用原生、未归档的 `text` 类型自定义属性。建卡以 `POST /api/issues` 同时传项目、已核验 Agent、初始状态键与 `properties: { "<属性UUID>": "mcp-dispatch-v1:<请求键摘要>" }`。有信箱来件时同时留存经核验的回程引用。属性和 Issue 在同一事务内提交。普通 `metadata` 需要后续写入，在两次请求之间可能丢失关联。`origin_type` 在此端点只接收原生 `quick_create`。[建卡字段](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/handler/issue.go#L3204-L3235) · [来源校验](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/handler/issue.go#L3574-L3600) · [Issue 写入事务](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/service/issue.go#L424-L488)
- `GET /api/issues` 带工作区、`project_id` 和 URL 编码的 `properties={"<属性UUID>":["<关联键>"]}`，有界分页后核完整性。再用 `GET /api/issues/{id}` 核实例、归属、属性和可信创建来源。属性可被编辑，须同时核对原件绑定。原生 `active_duplicate_issue` 按活跃标题和业务范围拦截，须独立核实其返回对象的精确关联。对象删除、改属性、迁移、权限变化及空结果都可能让对账失去证据。[项目筛选和分页](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/handler/issue.go#L1399-L1518) · [属性精确筛选](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/handler/property.go#L959-L1055) · [原生重复保护](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/service/issue.go#L391-L408)

## 副作用与证据

| 动作 | 原生语义和回读要求 |
|---|---|
| 新建并指派 | 普通建卡没有 `suppress_run`。具备资格的 Agent 或 Squad 可能在 Issue 提交后入队，backlog 和 triage 不走普通指派，离线 Agent 仍可能排队。建卡响应及读回确认 Issue。另查同一 Issue 的 `task-runs`，核实际执行对象、触发证据及精确 Run UUID。暂无匹配 Run 时保留待核。[提交后入队](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/service/issue.go#L587-L637) · [资格及离线语义](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/service/issue.go#L944-L1028) |
| 备注、评论、引导 | 纯记录用首词为 `/note` 的顶层评论，避开回复导致已解决线程重开。评论保存后才计算触发，普通评论可按提及、线程或指派关系触发。显式提及的 `trigger_outcomes` 只随写入响应返回。引导在途 Run 时查评论 `supplements[]` 的目标与投递状态，同时查是否回退到普通派发。编辑评论可能取消并重派相关 Run。[评论及 /note](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/handler/comment.go#L1931-L2019) · [引导与编辑](../../skills/multica-backend/references/access.md#状态交接与评论) |
| 改派、状态、复审 | 核原 Issue revision、当前指派、项目工作流和在途 Run。更新时传 `expected_revision`，冲突时回读。要暂缓执行时用 `suppress_run: true`，业务更新、工作流改派和可能的子任务联动仍会发生。进入 handoff 步骤可改派并开 Run。`stop_previous_assignee_runs` 需明确授权。读原响应的 `run_outcome` 与原卡、时间线和实际 Run。仅在原委托或项目流程要求时进入复审。[更新字段](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/handler/issue.go#L3762-L3810) · [交接语义](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/handler/issue_workflow_entry.go#L18-L115) · [派发回包](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/handler/issue_trigger.go#L101-L144) |
| 重跑、取消 | 先在原 Issue 下核完整 Run UUID。重跑产生新 Run，可能取消同一线程尚未开始的待执行项。取消后读原 Run 终态，另核已发生的外部动作和产物。Issue 的 `cancelled` 状态不会停止在途 Run。[精确 Run 的 CLI 和 REST 调用](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/cmd/multica/cmd_issue.go#L3304-L3402) · [状态副作用](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/handler/issue.go#L4423-L4446) · [重跑排队](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/service/task.go#L6263-L6292) |

每类写动作分别验收原生关联、期望执行和未知后的只读路径。相同状态、相同评论内容或时间接近的 Run 都不足以归因到某次写入。Run 终态、信箱回执和业务验收各沿其权威来源读回。[同 Issue 的 Run 查询](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/handler/daemon.go#L6437-L6585) · [协作规范](../../skills/workspace-coordination/SKILL.md#当前-issue-的下一步由谁执行)

## Python 接口及恢复

[`multica_backend.delivery`](../../mcp/multica_backend/delivery.py) 提供 `DeliveryLedger`、`DispatchCommand`、`NewIssue`、`IssueReference` 和 `NativeDispatch`。接入层在入口和恢复时核现时授权，并绑定固定实例。适配器提供配置的 `instance_id`，实现只读 `lookup` 与 `check_create`，以及认领后才调用的 `create_issue`。查找完整且没有匹配时返回 `None`，缺权限、结果不全或证据不可信时抛错。建卡请求只在精确读回证据后返回 `IssueReference`。适配器错误原样向调用层传播，调用层按原键用 `get` 读取最后持久状态，向外只暴露获权的脱敏诊断与收据。

```python
from multica_backend.delivery import DeliveryLedger, DispatchCommand, NewIssue

ledger = DeliveryLedger(private_state_path)
command = DispatchCommand(
    instance_id=instance_id,
    workspace_id=workspace_uuid,
    project_id=project_uuid,
    coordinator_id=agent_uuid,
    new_issue=NewIssue(title=title, status=initial_status_key, description=instructions),
)
ledger.accept(principal, request_id, command)  # 可独立受理，deliver 也会受理
receipt = ledger.deliver(principal, request_id, command, native)

# 恢复时逐一处理接入层管理且仍有有效权限的派发主体。
for request_id in ledger.list_pending(principal, state="accepted", limit=50):
    command = ledger.get_command(principal, request_id)
    if command is not None:
        native = authorize_and_select_native(principal, command)
        receipt = ledger.deliver(principal, request_id, command, native)
```

恢复分页用前页最后一个键作为 `after_request_id`，下一轮从头检查。获准对账的请求以 `state="unknown"` 分页走同一流程，认领条件阻止再次写入。失去授权时保留账本状态并回报。服务的发送进程共用本机持久 SQLite 文件，冻结指令和备份放在服务专有目录。账本丢失、回滚旧备份或改由独立写入节点时，先停新写并对账既有请求。确认回执和指纹的保留期覆盖业务重投期限。

## 备选与验证

单用原生属性，并发派发可同时查到空结果，因为属性可编辑且无唯一约束。单用 SQLite 可防本地竞争，缺少原生关联则无法定位响应丢失后的结果。组合持久认领和原子写入的原生关联增加一个私有账本，并保留少数需要查证的未知请求。如果新版原生写入支持持久幂等键和原结果读取，可用相同故障用例比较是否替换。

运行 `PYTHONPATH=mcp python3 -B -m unittest discover -s mcp/tests -p test_mcp_delivery_contract.py`。离线用例使用真实 SQLite、独立进程和模拟适配器，覆盖同键并发、同键异参、跨实例 UUID 重叠、已存在原单、受理后重启恢复、发送超时和认领后崩溃。上游语义核对 v0.11.0 固定源码。真实 HTTP 写适配器、隔离实例上的关联与权限，以及评论、状态、重跑、取消和精确 Run 的端到端回读仍需验收。
