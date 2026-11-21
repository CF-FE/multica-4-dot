# 原卡解阻通知账本

`unblock.ledger` 使用本机持久 SQLite 文件记录协调员提醒的发送认领和核回执。所有执行同一批登记的进程共用该文件。原卡静默摘要和所引用的原件继续提供业务状态。

## 调用接口

```python
reconcile(db_path, scope_key, checkpoint_id, send, lookup) -> dict
reconcile_existing(db_path, scope_key, checkpoint_id, lookup) -> dict
```

`scope_key` 由调用方从受信登记生成。CLI 以固定顺序将 `instance_id`、`workspace_id`、`project_id`、`issue_id`、`thread_id` 编码为紧凑 JSON 数组。`checkpoint_id` 代表该原卡线程中唯一的一轮待核事项。修订号、到期时间和来源事件编号可以变动，同一轮继续使用原检查点标识。新一轮才分配新标识。

`send(marker)` 最多执行一次发送尝试。`lookup(marker)` 沿登记中的原实例、原卡和原线程只读查询，核对精确 marker、调用身份和协调员提醒的原生证据。两个回调都只返回已核的 JSON 对象或 `None`。账本沿用原生适配器的回执结构，校验与原认领完全一致的 `marker`、`state: "started"`、标准 UUID `wakeup_id` 和 `run_id`，以及带时区的 ISO 8601 `started_at`。回调异常、空结果或回执不合约时都保留待核。数据库错误向调用方报告。

两种调用都返回 `status`、`marker` 和 `receipt`。

| `status` | `marker` | `receipt` | 含义 |
|---|---|---|---|
| `confirmed` | 原认领的 marker | 已核回执对象 | 已从发送或只读查询取得回执，后续调用可直接读本机缓存 |
| `unknown` | 原认领的 marker | `None` | 发送意图已经落盘，仍待查回执 |
| `not_found` | `None` | `None` | `reconcile_existing` 查无该作用域和检查点的本机认领 |

`unknown` 同时给出脱敏 `reason`。`receipt_pending` 表示回调尚未查到回执，`send_failed` 或 `lookup_failed` 表示对应回调抛出异常，`send_receipt_invalid` 或 `lookup_receipt_invalid` 表示回执未通过校验。有查询错误时优先报告查询原因。

账本先提交认领，再调用发送。多个进程同时命中时，只有成功插入该作用域和检查点组合的调用可发送。发送超时、拒绝、进程退出、响应丢失或回执暂时不可见时，保留原认领。后续查询即使返回空，也只沿原 marker 继续对账。SQLite 缓存回执时保留最先核到的版本。认领落盘后、发出请求前退出也保留 `unknown`，此时实际发送可能为零次。

信号消失或停用新提醒后，用相同数据库和原键调用 `reconcile_existing`。CLI 对应 `python3 -m unblock recover --config <登记> --db <账本> --issue <原卡> --checkpoint <原检查点>`。该入口仅在已有待核认领时查询远端，可以入账已核回执。查无认领时直接返回。保留账本文件以便重启后继续核对；不同文件各自拥有认领记录。

## 信号水位与重放

每轮扫描重读已登记原卡的完整原线程，核对当前协调员、登记范围、修订与检查点。最近一条有效静默摘要提供已核水位。补件使用原生作者、时间和摘要已引用的证据判定，精确 Run 使用已绑定记录的终态及原生发生时间，绑定 job 使用摘要中的 `mailbox_result_version` 与当前版本比较。到期条件从检查点的 `due_at` 重新计算。读取的是归属已核的持久来源，因此无需另设事件游标。读取失败或缺页时保留待核，下一轮完整重读，既有账本也无需回滚。

对晚到的记录，扫描应保留时间边界上的候选并用原生身份及引用核清，单凭 `timestamp > 上次扫描时间` 会漏掉晚可见或时间相同的记录。只要来源仍保留候选，即使扫描断开、信号乱序或到期与补件并发，下次完整扫描仍可重新判断。它们命中同一轮时共用同一键。若原生来源会丢弃尚未核收的候选，须由该来源提供可重放历史才有完整性保证。检查点切换后，旧轮的未知回执使用原键继续核对。
