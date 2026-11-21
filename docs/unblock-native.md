# Multica 原卡原生接入

`unblock.native.NativeSource(registration)` 使用受信本地登记。登记包含 `instance_id` 及完整 UUID `workspace_id`、`project_id`、`issue_id`、`thread_id`、`coordinator_id`。`thread_id` 是原卡线程的根评论 UUID。额外配置如下。

| 键 | 含义 |
| --- | --- |
| `cli_path` | 宿主当前 Multica CLI 的绝对路径 |
| `cli_profile` | 专用具名 profile |
| `origin` | 登记实例的 API origin，须与 profile 的 `server_url` 相同 |
| `expected_user_id` | 当前 API 调用账号的 UUID，通过 `/api/me` 核对 |
| `allow_private_http` | 可选。经运营者核准的加密私网 IPv4 origin 才设为 true |
| `notifications_enabled` | 可选。预览与停用使用默认的 false |
| `supplement_authors` | 可选。授权补件作者，形如 `[{"type":"member","id":"<UUID>"}]` |
| `run_id` | 可选。冻结的原 Run 完整 UUID |
| `mailbox` | 可选。冻结的原 job，形如 `{"job_id":"<ID>","payload_hash":"<SHA-256>","recipient":"<role>"}` |

在已授权进程中通过 `MULTICA_UNBLOCK_ACCESS_TOKEN` 提供操作者 PAT。适配器通过 `config show` 读回具名 profile 和 API origin，随后按实际服务端响应核对 `/api/me` 身份、项目和原卡归属、协调员及原线程。升级后复用宿主 CLI；发行号和提交号用于部署记录，兼容性取决于这些读取和唤醒回执所需的字段与语义。无法确认时返回待核原因。可选信箱读取沿用 `MULTICA_BACKEND_MAILBOX_*` 和既有 Mailbox 客户端。

`poll()` 返回 `snapshot`、`hints`、`pending` 和 `summary_source`。来源对象的 `comment_id`、`author_id`、`created_at` 取自通过核验的原生评论，时间保留服务端原值。原线程中须有现任协调员发布的 `/note unblock.v1 <JSON>`。JSON 带完整登记作用域、正整数 `revision` 和 `checkpoint_id`，见[记录格式](unblock-record-format.md)。适配器按登记 UUID 读取工作区内原生协调员，核对其未归档且 `system_key=mika`。修订用新静默备注追加，同一检查点修订严格递增。摘要的 `recorded_at` 可早于原生发布时间，后续事件以原生发布时间为准。

补件使用 `/note unblock.evidence.v1 <JSON>`。JSON 含六个登记作用域字段、当前 `checkpoint_id` 和非空 `evidence_ref`。补件须由登记的成员或智能体发布，并进入同一原线程。补件和精确 Run 终态采用原生时间戳，早于摘要的事件略过，同刻的事件保留为核收线索。绑定信箱时，摘要带已核的 `mailbox_result_version`，从 0 开始。适配器只用 `whoami` 和 `get_job`，沿原 job 比对归属、受信 payload 哈希和最新结果版本。

核心读取异常抛出 `NativeSourceError`，其 `.code` 为不含凭据或远端响应正文的固定诊断。可选来源缺证列入 `pending`。集成入口在来源待核时暂停新提醒。

`check_ready()` 在同一个实例成功 `poll()` 后只读核对当前写入条件。返回 `None` 表示当时可以认领新提醒，返回字符串表示固定待核原因。调用方先 `check_ready()` 再持久认领，`notify` 在 POST 前再次核对。已有认领的重启对账直接用 `lookup`。

`notify(marker)` 与 `lookup(marker)` 仅在查到精确提醒实际启动的 Run 后返回匹配回执。返回 `None` 表示待核，可能有已落盘的提醒规则。调用方持久认领后才调用 `notify`，重启、网络故障或返回 `None` 后沿同一 marker 执行只读 `lookup`。

## 原生提醒和停用

提醒使用当前 Issue 状态作为原生条件，向原卡原线程的登记协调员创建一次性 Issue wakeup。该条件最多有效 60 秒，到期按 `end` 处理。原卡已关、协调员同线程已有启用唤醒、或原卡已有在途 Run 时，保持待核。实际回执包含 `marker`、`wakeup_id`、`run_id`、`started_at` 和冻结的六个作用域字段。核对原规则的指令、类型、作用域、目标、创建账号、原线程和触发历史，再回原卡查同一 Run 的启动。启动只确认提醒送到该协调员的运行时。

固定版本的创建请求使用 `expires_in_seconds: 60`。原生列表读回字段为 `expiry_seconds: 60`，服务端还会按状态条件生成 `event_types: ["issue.status_changed"]`。列表须同时显示 `created_by_agent: false`、`source_task_id: null`、`revision: 1` 和固定的目标、来源及完整指令。跨进程 HTTP 夹具应按服务端列表契约构造此回读，尤其保留这些服务端生成的字段。

停用登记会停止新写入，已有计划仍由服务端处理。授权操作员用 `issue wakeup list <issue-id>` 或 `issue wakeup get <issue-id> <wakeup-id>` 精确核对 marker、创建者、目标、原线程和状态，再用 `issue wakeup runs <issue-id> <wakeup-id>` 核查已有执行。需要立即撤回时，对核实的原规则执行 `issue wakeup disable <issue-id> <wakeup-id>` 后读回规则和 Run。v0.11.0 的停用撤回关联的 `queued`、`deferred` 且未启动的 Run，已分发或已启动的 Run 要走原卡处理。保留规则便于对账。状态、归属或任职在最后一次客户端检查后仍可能变化，原生条件与服务端权限覆盖其中的状态和权限校验。

固定版本证据为 v0.11.0 的 [CLI 命令](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/cmd/multica/cmd_issue_wakeup.go)、[保存和回读端点](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/handler/issue_wakeup.go)、[核收规则及撤回查询](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/pkg/db/queries/wakeup.sql)。

## 夹具验证

`python3 -m unittest discover -s tests -p 'test_unblock_native.py' -v` 从仓库根目录运行。若环境已安装 MCP SDK，使用 `PYTHONPATH=mcp python -m unittest discover -s tests -p 'test_unblock_native.py' -v` 以仓库中的 `multica_backend` 为入口。夹具拦截所有 HTTP 请求和 CLI 调用。目标部署的原生调度与运行时实际启动留待另行授权的隔离验收。
