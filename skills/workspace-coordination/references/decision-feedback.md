# 回填一次实际选择

以原任务和已执行的工作单元为准。调用 `record_decision_feedback` 前从原记录取稳定的 Project、Issue、工作单元、Run 引用和发生时间。

| 部分 | v1 字段与含义 |
|---|---|
| 两类反馈的外壳 | `schema_version=1`、原 `project_id`、`event_id`、正整数 `revision`、`kind`、`decision_ids`、`subject_ref`、带时区的 `observed_at`、`execution_state`、`coverage_observation`、`payload`。已取得的 `execution_ref` 形如 `{"source":"multica","ids":{"run_id":"<实际 UUID>"}}`。 |
| 覆盖范围 | `coverage_observation` 含 `scope_ref`、`observed_at`、`scope_complete` 和 `units`。每项记录 `unit_id`、`state`（`pending`、`ended` 或 `unknown`）、`expects_result` 及可得的 `execution_ref`。只知道当前工作单元就用局部范围。 |
| 采用动作 | `kind=application` 的 payload 使用 `application_status`、`recommended_candidate_id`、`effective_candidate_id`、`reason_codes`、`evidence_refs`。后两项为数组。 |
| 执行结果 | `kind=result` 的 payload 使用 `execution_status`、`quality_status`、`result_refs`、`evidence_refs`。后两项为数组。只有观察到该单元结束才填 `execution_state=ended` 和明确终态。等待独立验收时填 `quality_status=pending`。 |

两类事件各用一个固定 ID。关联原生工作单元；必要时给可追溯的子单元使用稳定的适配器引用，并注明来源。返回 `received=true` 后按原决策读回反馈。原任务验收结论晚到时，沿同一结果事件提交完整的下一修订。协议拒绝格式时先核已经回收的事件，再纠正请求。状态变更已发生时仅重试反馈。[v1 合同、字段与 JSON 示例](https://github.com/CF-FE/decision-service/blob/0955a0870a607b74e134098a3be6458a9069f9a6/docs/api-contract.md#字面字段与最小样例)
