# ADR-005　Multica 上游发行跟踪与兼容基线

**状态**　Proposed · 2026-11-20（Asia/Shanghai）。本记录承接 [Dot 直连方案](001-dot-multica-gateway.md)的版本适配和升级证据。

## 背景与取舍

公子指出上游可能一周发版两次。只人工刷 Releases 容易遗漏中间版本。依赖更新工具能提示部分镜像或依赖变化，仍需人工核查自托管 API、镜像、CLI、Daemon 和数据库迁移。每日只读检查公开 Releases，保留本地验证和生产实施的各自证据，维护成本限于检查器和一份版本记录。

## 版本事实

| 事实 | 来源和当前证据 |
| --- | --- |
| 上游最新正式版 | GitHub `releases/latest` 标记的正式发布。2026-11-20 观察为 [`v0.11.1`](https://github.com/multica-ai/multica/releases/tag/v0.11.1)，Release ID `451169000`，`2026-11-19T10:12:27Z` 发布。 |
| 升级候选 | 公开、已发布、非预发布且按 `vMAJOR.MINOR.PATCH` 数字比较高于基线的 Releases。按版本列出全部具备评估资格的发布，每项附官方的基线至该版本变更链接。当前候选 `v0.11.1`，本轮核实了发布元数据与[标签指向的提交](https://github.com/multica-ai/multica/commit/e1fe10d6694848e35dd1aa00e08cd11d93e545ac)。 |
| 已核实的 Multica 部署比较基线 | [`v0.11.0`](https://github.com/multica-ai/multica/releases/tag/v0.11.0)，Release ID `449794198`，[固定提交](https://github.com/multica-ai/multica/commit/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8)。既有证据覆盖腾讯云镜像、readiness、迁移计数、备份库隔离恢复和已认证 CLI runtime 列表。浏览器重新登录、WebSocket、Daemon 新任务与附件业务读写在该回执中待验。[部署回执](../tencent-upgrade.md#2026-11-19-升级回执) · [CLI 版本证据](../../skills/multica-backend/references/cli-v0.11.0.md) |
| 候选版 MCP 实例读／写兼容性 | `UNKNOWN`。按启用能力分别进行隔离实例验证并记录结果。 |
| 实际生产 | 以有权读取的实例观测和时间为准。工具当前生产字段显示 `UNKNOWN`，另呈现最近入库的腾讯云只读观测。2026-11-20 实测运行中的 Web、backend 容器镜像标签均为 `v0.11.0`。[核实记录](../multica-backend-tasks.md#当前发行差距) |
| 未知或撤回 | 读取失败、分页不完整或版本身份不符时，对应事实标记 `UNKNOWN`，保留历史记录。已登记的候选若缺失、转预发布或同 tag 换了 Release ID，暂停评估并核对官方记录。确认撤回后，在版本记录的 `tracked` 条目加 `withdrawn_evidence` 链接，检查器将其排除，即使发布页仍可访问。两次检查间发布又撤下的版本可能漏记。 |

## 检查方式

在仓库根目录用 Python 3.10 或更新版本运行，脚本只用标准库。

```sh
python3 scripts/check_multica_release.py
python3 -m unittest discover -s tests -p test_multica_release.py
```

仓库启用 Actions 且默认分支已有[工作流](../../.github/workflows/check-multica-release.yml)后，计划每天 `01:23 UTC`（北京时间 `09:23`）运行，也可在 Actions 手动触发。GitHub 排队可能延迟实际开始。每轮先跑离线用例，再将 Markdown 报告写入 job summary。Checkout 仅有 `contents: read` 权限且关闭凭据保留，上游 GET 匿名读取。流程的输出止于运行日志和摘要。[定时触发说明](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onschedule) · [Job summary](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-commands#adding-a-job-summary)

固定 `multica-ai/multica` GitHub Releases 及 REST 版本 `2026-03-10`。连接与读取的空闲超时为 25 秒，列表按 `Link` 串行读取，每页最多 20 项、最多 20 页，支持压缩。实测 50 项的较大分页响应曾中途断开，改为 20 项后读通全量列表。传输中断或超时会重读一次。分别查询 `latest` 和全量列表，因为 GitHub 的 Latest 标记可能与数字最高的正式版不同。两份响应不一致时重跑核实。候选范围限于已发布的正式 Release，非标准正式标签的候选资格待人工核对。HTTP `429` 或带限流头的 `403` 按 `Retry-After` 或配额重置时间处理，检查器输出诊断后退出。`410` 复核固定 API 版本。最终仍有读取失败或结果不完整时返回非零并保留已读到的事实。成功表示发布元数据检查完成。[官方 Releases](https://github.com/multica-ai/multica/releases) · [REST Releases](https://docs.github.com/en/rest/releases/releases) · [分页](https://docs.github.com/en/rest/using-the-rest-api/using-pagination-in-the-rest-api) · [限流](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api) · [API 版本](https://docs.github.com/en/rest/about-the-rest-api/api-versions)

## 评估与回退

1. **核对版本跳跃。** 读基线之后每个正式版本的说明，以及基线至目标固定提交的差异，检查 Compose、迁移和适配路径。记录 Release ID、标签实际指向的完整提交、官方平台镜像摘要、CLI 和 Daemon 版本。Release ID 可发现同名重发，标签、内容及镜像摘要需在升级前另行核对。多个版本可作为一条跨版路径验证。上游有分步要求或隔离演练未通过时，按证据调整路径。[v0.11.0 → v0.11.1 固定提交差异](https://github.com/multica-ai/multica/compare/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8...e1fe10d6694848e35dd1aa00e08cd11d93e545ac)
2. **验证能力。** 在隔离实例用目标镜像和代表性数据验证迁移、恢复演练、readiness、授权与越权、分页、Issue／Run 读写、派发与静默、取消与回程契约。按实际启用范围复核 Web、CLI、Daemon 和附件。记录环境、身份、执行时间、版本和每项通过、失败或 `UNKNOWN` 的证据。必需字段、权限、归属或副作用改变时暂停受影响动作，待适配及复验后恢复。核验后人工更新[版本记录](../../compatibility/multica-releases.json)中的基线，生产实施后按实测另记实际版本并保留旧证据。候选初次纳入人工评估时，在 `tracked` 记录其 Release ID、观察日期和来源。[验证计划](../validation-plan.md)
3. **准备回退。** 沿腾讯云手册保存当前 Compose、镜像引用与摘要、PG17 dump、上传卷及配套配置，隔离恢复并保留证据。有证据表明新迁移尚未执行且旧应用兼容时可考虑切回旧镜像。迁移已执行或状态未知时，在独立 PG17 与新卷恢复同一备份时点的数据库和附件，用旧应用验 readiness、关键记录及附件，保留升级后原卷及变化证据。确认恢复时点、增量数据处置与原入口切换授权后再回切。[升级与恢复手册](../tencent-upgrade.md#6-升级失败和迁移后的回退)
