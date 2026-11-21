# 登记一个项目并核收解阻事项

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

## 字节验收与回退

只在实际获准的主机和路径使用下列命令。目标副本已存在即可读验；工具只产生内容证据。第一件、整批迁移和整卡的业务验收分别由指定人确认。[校验字段及系统差异](unblock-artifact.md)

```sh
python3 -m unblock verify-copy --source-root "$SOURCE_ROOT" --source-relative "$SOURCE_FILE" \
  --target-root "$TARGET_ROOT" --target-relative "$TARGET_FILE" \
  --expected-bytes "$EXPECTED_BYTES" --expected-sha256 "$EXPECTED_SHA256"
```

停用时先停止相应调度并关闭该登记的新通知，核对在途的原生唤醒及 Run；已存在的原生规则按[接入说明](unblock-native.md)核对或停用。保留账本和原回执，继续用 `recover` 或原生只读入口核对。原卡摘要、项目负责人和 G8 的既有人工流程仍可办理该件。
