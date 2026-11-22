# 已登记机器通道的接手协议

仅当原件由以下机器通道核收时使用。业务签收、实际执行和验收范围仍在原卡分别取证。

## 信箱委托接单

1. G8 从 Task Mailbox 按 `job_id` 读回原件，记录原件状态、`payload_hash`、实例、工作区、项目、现任协调员和稳定 `request_id`，冻结建卡或关联参数。经认证的发件人或获授权操作人显式调用 `dispatch_issue`。网关使用独立只读身份校验原 job 的摘要、范围与回程，并检查现任登记。确认没有原卡或指派时才发起一次建卡和指派。已有唯一原卡时使用 `original_issue_id` 关联。响应超时先查 `get_dispatch` 和原卡，随后沿同一身份、请求 ID 和参数对账。
2. 原卡已关联、经获准的原生 Issue 和 Run 读取确认尚未指派且无相关执行，且本件明确授权启动时，操作人可用 `update_issue` 指派现任协调员一次。保存独立于 `dispatch_issue` 的固定操作 `request_id` 和原生 `expected_revision`，传入 `assignee_type=agent`、`assignee_id` 和 `start_run=true`。已有指派、相关 Run 或写入结果不明时，沿原卡和原操作回执对账，补可验证的接手证据。
3. 接手的协调员在原卡核对原 job、摘要、项目和实际接手人，用自己的原生 Agent 身份写一次顶层静默备注。下面的 JSON 值取自该件，整行写入同一备注。用 `multica issue comment add <issue-id> --content-file <file>`，提交以后按原 Issue 读回。响应丢失时先查备注和原 ID，在证据不足时保留待核，不追加第二条。发件人或网关成员账号提交的备注仅作跟进记录。

   ```text
   /note {"event":"mailbox-intake-v1","job_id":"<job-id>","payload_hash":"<sha256>","issue_id":"<issue-uuid>","coordinator_id":"<agent-uuid>"}
   ```

4. G8 带同一个派发 `request_id`、`job_id` 和原作用域调用 `get_dispatch_acceptance`，核对 `issue`、摘要、协调员，以及 `acceptance.receipt` 的实际作者、原生评论 ID 和服务端时间。已有历史卡且尚无唯一可信绑定时，保留「接单未确认」，由原发件人或获授权操作人记录原卡线索、跟进人及下一个复查时间或事件。权限不足、读取截断、回执歧义时同样处理。恢复沿原登记对账。
5. 回报分别引用四项证据。Task Mailbox 原 job 的 `PERSISTED` 是信箱保存。`acceptance.state=accepted` 是协调员接手。`run.state=started` 带原生 `id` 和 `started_at`，表示同卡同 Agent 处理这笔 job 的 Run 已启动。网关通过原生备注的 `source_task_id` 定位该 Run，随后核验原生运行时间。缺少绑定的同卡 Run 只作候选，`queued` 仍在等待。历史卡通过 `update_issue` 指派时，核对该操作的 `run_outcome` 和可归因的同卡、同 Agent 精确 Run。归因或启动时间缺证时保留待核。指定验收人按交办约定记录业务验收。信箱的 `RESULT_READ_ACKNOWLEDGED` 只记录收件方读取指定结果版本。

## 腾讯 unblock 动作签收

由登记动作的具名执行人用本人身份在原根线程回复静默备注。替换下例的所有占位值；也可用目标已登记的 `request_id` 代替 `checkpoint_id` 和 `step`。协调员读回原生作者、服务端创建时间和评论 UUID，再将 `multica:comment:<评论 UUID>` 及该原件的绑定字段写入核收摘要。精确协议备注保持独立格式，在同一 Run 可继续原授权内的工作。

```text
/note unblock.pickup.v1 {"thread_id":"<原根评论 UUID>","checkpoint_id":"<检查点>","step":"<动作>","target_id":"<目标>","target_version":"<版本>"}
```

接手证据须绑定原线程、本次动作或原请求、目标及版本。在登记协议中，项目负责人据对应 Run 和产物签认恢复，指定验收人按验收范围签认。读到旧版本或来源不清时标待核，按原标识只读对账。
