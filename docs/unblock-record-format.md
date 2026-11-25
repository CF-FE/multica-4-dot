# 原卡解阻记录 v1

`unblock.model.assess(registration, snapshot, now)` 接收两个 JSON 对象和带时区的 Python `datetime`，返回可序列化的判断结果。登记由本地受权来源提供。原生读取层须从原卡固定线程核对真实作者、现任协调员及修订顺序，再把静默备注 `/note unblock.v1 <JSON>` 的 JSON 交给模型。模型须在任何核收提醒前通过校验。

## 供 CLI 对接的登记与摘要

下面外层对象用于展示同一组参数。`snapshot` 本身是备注正文中的 JSON。所有值均为隔离示例。

```json
{
  "registration": {
    "instance_id": "fixture",
    "workspace_id": "00000000-0000-4000-8000-000000000001",
    "project_id": "00000000-0000-4000-8000-000000000002",
    "issue_id": "00000000-0000-4000-8000-000000000003",
    "thread_id": "00000000-0000-4000-8000-000000000004",
    "coordinator_id": "00000000-0000-4000-8000-000000000005",
    "checkpoint_id": "first-copy",
    "required_evidence": ["technical", "business", "isolation"],
    "roles": {
      "coordinator": {
        "id": "00000000-0000-4000-8000-000000000005",
        "name": "示例协调员",
        "appointment_ref": "fixture:coordinator-appointment",
        "valid_from": "2026-11-01T00:00:00+08:00",
        "valid_until": null
      },
      "project_lead": {
        "id": "00000000-0000-4000-8000-000000000006",
        "name": "示例负责人",
        "appointment_ref": "fixture:lead-appointment",
        "valid_from": "2026-11-01T00:00:00+08:00",
        "valid_until": null
      },
      "acceptor": {
        "id": "00000000-0000-4000-8000-000000000007",
        "name": "示例验收人",
        "appointment_ref": "fixture:acceptor-appointment",
        "valid_from": "2026-11-01T00:00:00+08:00",
        "valid_until": null
      },
      "g8": {
        "id": "00000000-0000-4000-8000-000000000008",
        "name": "示例云端发件人",
        "appointment_ref": "fixture:g8-appointment",
        "valid_from": "2026-11-01T00:00:00+08:00",
        "valid_until": null
      },
      "technical": {
        "id": "00000000-0000-4000-8000-000000000009",
        "name": "示例技术取证人",
        "appointment_ref": "fixture:technical-appointment",
        "valid_from": "2026-11-01T00:00:00+08:00",
        "valid_until": "2026-12-01T00:00:00+08:00"
      }
    }
  },
  "snapshot": {
    "instance_id": "fixture",
    "workspace_id": "00000000-0000-4000-8000-000000000001",
    "project_id": "00000000-0000-4000-8000-000000000002",
    "issue_id": "00000000-0000-4000-8000-000000000003",
    "thread_id": "00000000-0000-4000-8000-000000000004",
    "coordinator_id": "00000000-0000-4000-8000-000000000005",
    "checkpoint_id": "first-copy",
    "revision": 1,
    "recorded_at": "2026-11-21T14:00:00+08:00",
    "due_at": "2026-11-21T15:00:00+08:00",
    "decision_due_at": "2026-11-21T16:00:00+08:00",
    "target": {"id": "fixture:first-copy-destination", "version": "v1", "step": "生成首件", "acceptance_scope": "first_item"},
    "activity": "clear",
    "pickup": {
      "ref": "fixture:lead-pickup",
      "actor_id": "00000000-0000-4000-8000-000000000006",
      "at": "2026-11-21T13:00:00+08:00",
      "target_id": "fixture:first-copy-destination",
      "target_version": "v1",
      "checkpoint_id": "first-copy",
      "step": "生成首件",
      "source_scope": {
        "instance_id": "fixture",
        "workspace_id": "00000000-0000-4000-8000-000000000001",
        "project_id": "00000000-0000-4000-8000-000000000002",
        "issue_id": "00000000-0000-4000-8000-000000000003",
        "thread_id": "00000000-0000-4000-8000-000000000004"
      }
    },
    "evidence": {
      "technical": {
        "ref": "fixture:technical-readback",
        "actor_id": "00000000-0000-4000-8000-000000000009",
        "at": "2026-11-21T13:30:00+08:00",
        "source_scope": {
          "instance_id": "fixture",
          "workspace_id": "00000000-0000-4000-8000-000000000001",
          "project_id": "00000000-0000-4000-8000-000000000002",
          "issue_id": "00000000-0000-4000-8000-000000000003"
        },
        "target_id": "fixture:first-copy-destination",
        "target_version": "v1",
        "valid_until": "2026-11-21T18:00:00+08:00",
        "result": "confirmed"
      }
    },
    "contacts": {
      "isolation": {"name": "入口联系人", "ref": "fixture:contact-lead"}
    }
  }
}
```

上例在北京时间 2026-11-21 14:00 得到 `state=blocked`、`next_action=request_g8_review`、`g8_pending=true` 和 `checkpoint_due=false`。此时技术取证已核，业务许可与隔离还缺有权补证人。协调员落实对口。已约定向 G8 回报的任务，G8 可沿原委托看到该缺口。

### 单项任务的最小输入

下例只有一个必需项 `data_version`，暂无接手或补件，得到 `awaiting_pickup`。CLI 的项目目录可将实例、工作区、项目、协调员和职责索引置于项目 `defaults`，将原卡、原线程、检查点及本件必需项置于 `cases`，由入口合并成以下登记。实际原生读取还需要 [原生接入配置](unblock-native.md)。

```json
{
  "registration": {
    "instance_id": "fixture",
    "workspace_id": "00000000-0000-4000-8000-000000000001",
    "project_id": "00000000-0000-4000-8000-000000000002",
    "issue_id": "00000000-0000-4000-8000-000000000003",
    "thread_id": "00000000-0000-4000-8000-000000000004",
    "coordinator_id": "00000000-0000-4000-8000-000000000005",
    "required_evidence": ["data_version"],
    "roles": {
      "coordinator": {
        "id": "00000000-0000-4000-8000-000000000005",
        "name": "示例协调员",
        "appointment_ref": "fixture:coordinator-appointment",
        "valid_from": "2026-11-01T00:00:00+08:00",
        "valid_until": null
      }
    }
  },
  "snapshot": {
    "instance_id": "fixture",
    "workspace_id": "00000000-0000-4000-8000-000000000001",
    "project_id": "00000000-0000-4000-8000-000000000002",
    "issue_id": "00000000-0000-4000-8000-000000000003",
    "thread_id": "00000000-0000-4000-8000-000000000004",
    "coordinator_id": "00000000-0000-4000-8000-000000000005",
    "checkpoint_id": "data-1",
    "revision": 1,
    "recorded_at": "2026-11-21T14:00:00+08:00",
    "due_at": null,
    "target": {"id": "fixture:data-export", "version": "v1", "step": "核对待交数据", "acceptance_scope": "issue"},
    "activity": "unknown",
    "evidence": {}
  }
}
```

## 字段与原件

登记与摘要中的实例、工作区、项目、原卡、原线程和协调员必须逐项一致。`revision` 是从一开始递增的原卡摘要修订号，同时以原生历史检查同号冲突和倒退。日常使用协调员签认的 `snapshot.checkpoint_id`。试点可填写 `registration.checkpoint_id` 固定预期轮次。同一核收轮次的补件与到期共用该 ID，重新登记独立检查点时生成从未使用的新 ID。`recorded_at` 是协调员签认该修订的时间。`due_at` 为空时只等事件。`decision_due_at` 可选，记录最迟决定时间。到期仍缺证据时，v1 输出待跟进的提示，由协调员在原卡落实有权对口。`no_local_action` 可选，表示同因重现且协调员核实当前没有可行的本地动作。

`required_evidence` 明确列出本件恢复所需的证据，不能为空或重复。每项以一个小写字母开头，后续可用小写字母、数字和下划线，总长不超过 64。每项与 `roles` 中的同名职责相配。无任职依据时省略该角色。首件场景的 `technical`、`business`、`isolation` 分别指技术能力、有效业务许可、生产隔离。任一职责缺失只影响该项。保留键 `coordinator`、`sender`、`project_lead`、`acceptor`、`g8`、`disposition` 分别用于原卡核收、派发对账、负责人接手与恢复、指定验收、G8 的跨端收件回证与有权方正式处置。G8 按协作规范以云端发件人或结果收件人登记。业务验收和正式处置各登记实际有权方。`coordinator` 为必填，其 ID 及任职窗口须覆盖摘要签认和评估时点。

角色以 `appointment_ref` 记录任职原件，窗口左闭右开。取证依据和授权原件须分别核对对象、版本、职责和发生时间。时间用含秒与时区的 ISO 8601 字符串，`valid_until=null` 表示原件未设结束时间。所有来源记录的 `at` 最迟为该修订的 `recorded_at`。每条记录携带 `ref`、`actor_id`、`at`、`source_scope`。其中 `source_scope` 的四项表达原件核实后实际覆盖的实例、工作区、项目和原卡。外部原件仍以其自身引用留存，摘要须能证实其覆盖当前案。引用由协调员验证输入来源，模型校验已签认数据的关联与权限边界。

| 摘要字段 | 在通用来源字段之外填写 |
| --- | --- |
| `pickup` | 具名执行人在原单明确承接本动作的原生回执，附下文的动作绑定字段。协调员签认摘要时核实原件作者、动作及版本 |
| `activity` | `clear` 表示相关在途与原产物已核清，可评估后续；`unknown`、`in_flight`、`artifact_unconfirmed` 分别记录查证未完成、在途、原产物待只读核对 |
| `target` | `id`、`version`、`step`、`acceptance_scope`。可用 `expected_evidence` 写明要交回的具体证据，用 `request_id` 关联原交办。`executor_id` 填原卡具名执行人；尚待协调员落实时填 `null`，省略时沿用登记的项目负责人 |
| `evidence.<key>` | `target_id`、`target_version`、`valid_until`、`result`。结果为 `confirmed` 或 `rejected`；没有原件则省略该项 |
| `contacts.<key>`、`pursuers.<key>` | 联系人填写 `name`、`ref`，追证人另带 `id`。两类均为线索或安排，有权补证者从职责索引读取。无追证人时由协调员跟进 |
| `g8_request` | `request_id` 标识沿原委托发给 G8 的跟进记录，绑定当前原线程、目标、版本、检查点和动作。绑定原信箱时，`job_id` 须与登记的 `mailbox.job_id` 一致，且摘要须有非负整数 `mailbox_result_version`。可附 `read_ack_ref` 记录已读 |
| `g8_acceptance` | 引用 G8 的跨端收件回证，填同一个 `request_id`、原卡已核实的 `next_owner_id` 及 `next_check_at` 或 `next_check_event`。回证不得早于请求，定时检查须晚于回证。事件须能从约定的原生补件、指定 Run 或原 job 观察到。执行接手使用独立的 `pickup` 原件 |
| `execution` | 本动作的绑定字段、`run_id`、`artifact_id`。引用项目负责人对实际成功执行和产物的回证，时间记录该次执行时点 |
| `acceptance` | 本动作的绑定字段、相同的 `run_id` 和 `artifact_id`、`scope`、`result`。范围为 `first_item` 或 `issue`，结论为 `accepted` 或 `rejected` |
| `disposition` | `target_id`、`target_version`、`reason`、`status`。暂停填 `paused` 及 `resume_condition`，取消填 `cancelled` |

## CLI 消费评估结果

**如何把回执绑定到当前动作。** `pickup`、`execution`、`acceptance` 都填写原件的 `source_scope.thread_id`、`target_id` 和 `target_version`。再匹配本次 `checkpoint_id` 和 `step`，或匹配目标登记的原交办 `request_id`。原件同时带多个标识时逐项核对。复查与重放沿用原 ID；独立新动作使用新标识。并行支路在同一 Issue 的不同固定线程分别登记取证和验收范围。

在 Multica 原生入口，具名执行人用本人身份在原根线程回复一条静默接手备注。例如：

```text
/note unblock.pickup.v1 {"thread_id":"<原根评论 UUID>","checkpoint_id":"review-P089","step":"核对原音登记与字幕片段","target_id":"P089","target_version":"subtitle-v2"}
```

协调员在摘要中引用 `multica:comment:<这条接手评论的 UUID>`，按原件填写作者、服务端创建时间和相同的绑定字段。读取器在原线程核对作者、未编辑及未删除状态、时间和正文。当前动作的接手声明缺少对应原件时，巡查仍展示“待接手”，暂停新发并核实原引用。回执格式用在已登记的动作级交接。

评估通过 `executor_id`、`pickup_status` 和 `pickup_ref` 展示本动作的执行人、接手状态和有效回执；`recorded_pickup_ref` 保留原摘要引用供追溯。`next_check_at` 或 `next_check_event` 展示复查时间或约定事件。旧摘要缺少动作绑定时仍可读取，当前动作保持待接手。由执行人补本次原件，协调员在原线程追加新修订，保留此前备注。指定执行人承接只证明该人接手，恢复与放行仍沿原授权和指定验收人取证。

评估只有三种 `state`。缺负责人接手为 `awaiting_pickup`，已接手而受阻步骤尚无完整恢复依据为 `blocked`，受阻步骤的实际执行、产物及当时所需权限已核为 `recovered`。实际恢复后才评估验收，`accepted_scope=first_item` 只表示首件已验，`issue_accepted` 仅在目标与指定验收人均明确覆盖整卡时为 true。

`next_action` 优先处理已确认的暂停和取消，其次核对未知或在途活动，再处理取证、恢复和验收。核对发现已有产物时，先沿原记录只读核实与补回证。`verify_and_resume` 由项目负责人沿原授权核对并恢复一次。`owner_id` 标明下一步负责人，缺接手回证时由登记发件人、或默认协调员对账。未通过的验收交回相应范围复核。

`g8` 只读清单沿用 v1 的 `g8_pending`、`request_g8_review`、`follow_g8_plan` 等既有枚举。它从登记中筛出待接手、需查看和部分待跟进的事项。原 Issue 和原委托提供完整的业务状态。`g8_status=accepted` 表示模型核到匹配的 G8 回证。程序从回证取 `next_owner_id` 和复查点，供原线程跟进使用。仅约定事件时 `checkpoint_due=false`，由原生读取层提交已核实的事件线索。旧摘要若仍将业务动作交给 G8，协调员沿原线程核对实际接手人，再补发同一动作的新摘要修订。保留旧回执和原检查点账本。

暂停、取消和相应范围验收完成时 `notification_open=false`。`close_cancelled` 和 `record_issue_acceptance` 是只读评估结果，分别依据已登记的正式处置记录或验收人回证。自动通知入口检查 `notification_open` 和到期或有效事件，收件人固定为已核实的现任协调员。

必填字段缺失、类型错误、未来签认时间、错项目和错请求返回 `ValueError`。角色、证据时效或目标关联待核时，评估保留相应状态和引用。未知活动、权限读取失败和不全的来源应沿原卡查证。模型只负责评估，修订历史与原件归属由读取层核验，通知、对账及是否开始原动作分别沿既有入口处理。
