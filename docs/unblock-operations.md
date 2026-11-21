# 登记一个项目并核收解阻事项

**升级按[版本兼容规范](../AGENTS.md#unblock-版本兼容)办理。** 依次核对具名 profile、API origin、原卡范围、只读预览、一次真实提醒和同键重放；记录实测版本及具体缺项。

从仓库根目录运行 `python3 -m unblock`，Python 3.11 及以上。以下命令中的 `cases.json`、`snapshot.json` 和 SQLite 均为操作者私有文件；案例使用占位标识。本地方案、隔离回执和真实业务验收分别登记。[设计](project-unblock-loop.md) · [ADR-006](decisions/006-project-unblock-loop.md)

## 准备与发布摘要

1. 从已核的项目任职和原 Issue 登记实例、工作区、项目、协调员及有权方；为不同事项选择本件需要的证据。为固定线程记录原卡和根评论 UUID。同一项目的岗位、客户端绑定和权限依据可复用。`cases.json` 采用以下外层结构，`defaults` 与单卡字段互斥。实际字段、岗位和证据示例分别见[摘要格式](unblock-record-format.md)与[原生接入](unblock-native.md)。

   ```json
   {
     "projects": [{
       "defaults": {
         "instance_id": "<实例>", "workspace_id": "<工作区 UUID>", "project_id": "<项目 UUID>",
         "coordinator_id": "<协调员 UUID>", "roles": {},
         "cli_path": "<multica 绝对路径>", "cli_profile": "<具名 profile>",
         "origin": "<已核 API origin>", "expected_user_id": "<操作者 UUID>"
       },
       "cases": [{
         "issue_id": "<原卡 UUID>", "thread_id": "<根评论 UUID>",
         "required_evidence": ["technical", "business", "isolation"], "notifications_enabled": false
       }]
     }]
   }
   ```

2. 协调员核源证据后准备快照。用下列命令校验并生成静默备注，再以**协调员本人原生 Agent 身份**在原线程发布；精确读回作者、根评论、修订号和目标。单调增加修订号，保留原备注。同一核收事项沿用检查点 ID；确有独立的下一项工作才取新 ID。

   ```sh
   python3 -m unblock prepare-note --config cases.json --issue "$ISSUE_ID" --snapshot snapshot.json
   ```

3. 原生读取只用已登记的服务和身份。把专用凭据从获准的环境入口提供给运行进程。绑定信箱时核原 job、原摘要、收件人和协调员已核的原结果版本。源不可用或有歧义的卡单独显示待核。普通文本、接口入箱和资源绑定都不能签发岗位任职或业务许可。

## 日常入口

```sh
python3 -m unblock summary --config cases.json --issue "$ISSUE_ID"
python3 -m unblock g8 --config cases.json
python3 -m unblock tick --config cases.json
```

`summary` 返回最近一次由协调员核收的摘要、原评论、各项条件、责任人及来源增量。`basis=coordinator_reviewed_summary` 表示程序核了摘要作者和原线程，并根据登记与引用计算下一步；实际业务授权、产物来源及验收语义仍由有权人对照引用的原件核准。`g8` 列出等待 G8 处置和已由 G8 接手且仍归其办理的事项，并披露读取不完整的范围。`tick` 默认预览。在另行获准的项目，将指定登记的 `notifications_enabled` 设为 `true` 后，才使用下列实际通知命令。可以挂到现有调度器，每次完成就退出；只读取所列项目与卡。单卡试点使用 `--issue`，保存同一私有 SQLite 的绝对路径。

```sh
python3 -m unblock tick --config cases.json --issue "$ISSUE_ID" --db "$LEDGER" --apply
python3 -m unblock recover --config cases.json --issue "$ISSUE_ID" --checkpoint "$CHECKPOINT" --db "$LEDGER"
```

原线程补件、信箱新版本和到期是同一回合的触发线索。原卡已有执行或合适的在途唤醒时显示 `deferred` 及原因，常规预检不会消耗本轮认领。结果不明先 `recover`，用原通知和实际开始的精确 Run 确认投递；协调员接手仍取其单独回证。输出中的 `source_reads_complete` 表示数据覆盖情况，`notifications_unconfirmed` 计数仍待核的发送。新的账本文件会丢失旧认领历史，须保护并备份原文件。判定可恢复时，项目负责人核对最新授权和在途，沿原卡执行；该命令集不直接执行项目工作。

## 腾讯协调端与 G8 原卡交接

腾讯 VPS 的 [systemd 定时器](../deployment/unblock/multica-unblock.timer) 在上一轮结束约一分钟后启动检查。它只处理私有登记中开启提醒的卡。原生 API 走回环，各协调员所属的 Daemon 领取 Multica Run。Windows 原启动脚本保留只读操作。

腾讯写入口使用 `cases.json` 顶层的 `"appointment_ssh_config": "/etc/multica-unblock/appointment-ssh.conf"`。任命只在云网关办理。同一工作区的卡共用最近一次核实的任命，缓存位于原 SQLite 账本的 `unblock_appointment_cache` 表。没有启用卡或已缓存且原卡线索未变的空扫不会连接 Vultr。首次缺缓存，或原生摘要、受信交接出现较新的不同协调员时，按工作区刷新。线索本身不能指定提醒对象。

真正新建提醒前实时核对工作区、协调员、网关运行代次及激活时刻。查询失败或发现换任时，本次发送暂缓；只有确定未进入原生 POST 才释放本轮空认领。网络恢复后，下次巡检使用原检查点重新核验。已发提醒沿原 marker 和原 Run 对账。新增工作区时按[只读身份说明](../deployment/unblock/appointment-ssh.md)登记可读范围。

换任后由新任在原线程核收并签发摘要，原检查点和 SQLite 账本继续使用。网关没有逐工作区的任职生效时间，因此取本次网关激活时刻作为可证的最早时间；即使人员未变，网关重启前的旧摘要也需要重新核收。已经提交给 Multica 的唤醒由平台继续处理。严格交接时先停止该范围的新提醒，核清旧任仍在途的规则和 Run，再使新任命生效。客户端的最后一次查询与平台收件跨越两个服务。

1. 对获准接收巡查交接的卡，在登记增加 `handoff_member_id`。从一次网关静默备注的原生作者读回成员 UUID。协调员先在固定原线程发布带检查点的摘要。网关备注作者、接收提醒的协调员、运行该协调员的宿主分别核对。
2. G8 核到新阻塞时，用现有 Multica 网关的 `add_issue_note` 在原卡留顶层静默备注。请求沿原实例、工作区、项目、Issue 和固定 `request_id` 办理。`content` 为 `unblock.handoff.v1 ` 加 JSON，包含 `instance_id`、`workspace_id`、`project_id`、`issue_id`、`thread_id`、`coordinator_id`、`checkpoint_id` 和 `evidence_ref`。工具自动添加 `/note `。原执行端读回 `comment_id`；响应未知时沿同一请求对账。
3. 腾讯端核对作者、原线程、检查点和创建时间。日志里的 `patrol_handoff:<评论 ID>` 可以追到本次提醒的输入。用原生 wakeup 的触发记录核对实际启动的 Run，再读 Mike 的原线程回证。多个客户端共用网关身份时，具体是哪一次 G8 巡查写入，还须与 G8 自身回执关联。
4. 验证因果关系时，隔离卡的 `due_at` 设为 `null`，先观察一次自然巡检得到 `quiet`，再发静默交接。下一轮和后续重放应取得同一提醒、Run 和服务端启动时间。新增业务卡须登记实际授权、协调员及原线程。

部署入口在 [deployment/unblock](../deployment/unblock/)。升级 Multica 后运行 `sudo /opt/multica-unblock/sync-cli`，再按版本兼容规范复验。停用腾讯端可执行 `sudo systemctl disable --now multica-unblock.timer`，等待当前服务退出并核查在途提醒。切回其他主机时，先停原发送端，转移并核验**最新** SQLite 账本，再启用一个发送端。

## 字节验收与回退

只在实际获准的主机和路径使用下列命令。目标副本已存在即可读验；工具只产生内容证据。第一件、整批迁移和整卡的业务验收分别由指定人确认。[校验字段及系统差异](unblock-artifact.md)

```sh
python3 -m unblock verify-copy --source-root "$SOURCE_ROOT" --source-relative "$SOURCE_FILE" \
  --target-root "$TARGET_ROOT" --target-relative "$TARGET_FILE" \
  --expected-bytes "$EXPECTED_BYTES" --expected-sha256 "$EXPECTED_SHA256"
```

停用时先停止相应调度并关闭该登记的新通知，核对在途的原生唤醒及 Run；已存在的原生规则按[接入说明](unblock-native.md)核对或停用。保留账本和原回执，继续用 `recover` 或原生只读入口核对。原卡摘要、项目负责人和 G8 的既有人工流程仍可办理该件。
