# Multica 候选版隔离验证

2026-11-20 从官方 Releases 读到最新正式版 `v0.11.1`。本轮固定比较 `v0.11.0` 的 `cb190810a659c1a61c4a86d9f6ecfc9df4b086d8` 与 `v0.11.1` 的 `e1fe10d6694848e35dd1aa00e08cd11d93e545ac`，两个标签的 Git ref 已读回。后续发版先运行发布检查器，再按实际目标更新验证清单中的 tag、commit 和固定提交对应的源码 SHA-256。[本轮版本清单](../compatibility/candidate_versions.json) · [正式发行](https://github.com/multica-ai/multica/releases/tag/v0.11.1) · [固定提交差异](https://github.com/multica-ai/multica/compare/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8...e1fe10d6694848e35dd1aa00e08cd11d93e545ac)

## 运行入口

在仓库根目录用 Python 3.10 或更新版本运行。

```sh
python3 scripts/check_multica_candidate.py
python3 scripts/check_multica_candidate.py --source
python3 scripts/check_multica_candidate.py --isolated
```

- 默认运行离线测试，用合成记录验证源码检查、预检拒绝和原生结果解析。上游 Go `TestMain` 在数据库不可用时可能以 0 退出，运行器因此要求每项预期测试都有 `run` 和 `pass` 事件。[上游 TestMain](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/cmd/server/integration_test.go#L44-L99) · [离线测试](../tests/test_multica_candidate.py)
- `--source` 从固定提交读取 REST 路由、Issue 范围 Run 列表以及 `/note` 和 `trigger_outcomes` 的源码。报告证据为 `fixed_source_inspection`。GitHub 限流时，可以运行 `--source --source-dir /path/to/snapshots`，按 `<目录>/<完整 commit>/<上游文件路径>` 放置从该提交取得的原始文件。两种读取方式均校验 SHA-256。失败的检查显示 `unknown`，已核实的检查保留结果。[基线路由](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/cmd/server/router.go) · [候选路由](https://github.com/multica-ai/multica/blob/e1fe10d6694848e35dd1aa00e08cd11d93e545ac/server/cmd/server/router.go) · [候选 Run 列表](https://github.com/multica-ai/multica/blob/e1fe10d6694848e35dd1aa00e08cd11d93e545ac/server/internal/handler/daemon.go) · [候选评论触发](https://github.com/multica-ai/multica/blob/e1fe10d6694848e35dd1aa00e08cd11d93e545ac/server/internal/handler/comment.go#L1948-L2014)
- `--isolated` 使用一份可用的本地 Docker daemon、Git、与固定源码 `server/go.mod` 相符的 Go 工具链和访问公开依赖的网络。Docker 缺省使用 `/var/run/docker.sock`，可用 `--docker-socket` 提供已确认的一次性本地 daemon 的 Unix socket 绝对路径。运行器校验两个 checkout 的 commit，为每版分配独立的临时 PG17、回环随机端口和随机凭据，执行上游迁移及原生 HTTP 测试，最后清理自己的容器及临时工作目录。这个模式使用上游 Go 测试服务器、PG17 和假运行时观察排队，证据为 `native_source_router`。数据库镜像使用上游 CI 的公开 `pgvector/pgvector:pg17` 并记录实际镜像 ID。[上游 CI](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/.github/workflows/ci.yml#L348-L455) · [原生用例](../compatibility/candidate_native_test.go)

两种有报告的模式输出一行 JSON。可读取 `evidence`、`versions[].tag`、`versions[].commit`、`versions[].checks` 和 `release_image_compatibility`。退出码 `0` 表示该证据层面的全部检查通过，`1` 表示至少一项有失败证据，`2` 表示前置条件或证据不全。发行镜像在这两个模式下均显示 `unknown`。

### GitHub 托管隔离运行

仓库启用 GitHub Actions，且[候选验证工作流](../.github/workflows/check-multica-candidate.yml)进入默认分支后，有仓库写权限的操作者可在 **Actions → Check Multica candidate in isolation → Run workflow** 选择包含已审定版本清单的分支。首次运行选择默认分支 `main`，也可使用 `gh workflow run check-multica-candidate.yml --ref main`。触发事件仅为 `workflow_dispatch`。[GitHub 手动触发说明](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)

工作流在 GitHub 托管的 Ubuntu 24.04 上用固定 Go 1.26.9 执行 `--isolated`，限时 45 分钟。每次运行使用所选提交中的版本清单和 runner 自身的 Docker daemon。打开该次运行的 **Summary** 查看原始 JSON 和脚本退出码，脚本返回非零时检查步骤失败。GitHub 托管执行待首次触发取证。[托管 Ubuntu 软件清单](https://github.com/actions/runner-images/blob/main/images/ubuntu/Ubuntu2404-Readme.md)

## 原生用例和对账条件

| 检查 | 通过条件 |
| --- | --- |
| `identity` | 未登录访问 `/api/me` 返回 401。一次性登录凭据返回预期测试账户。 |
| `project_issue_run_ownership` | 创建项目与 Issue 后回读所属 workspace、project 和 Issue，再通过 `scope=issue&view=timeline` 查回关联 Run 的 ID、Issue、workspace、agent 及触发评论。 |
| `cross_workspace_read_and_write_denied` | 另一测试工作区账号读取目标项目、Issue、Run 或写评论时返回 403 或 404。从目标工作区复核评论和待执行队列均无新增。 |
| `silent_comment_saved_without_run` | `/note` 带明确的测试 agent 提及。评论保存并回读成功，触发回执、补充指令和 Run 均为空。 |
| `normal_comment_receipt_and_run` | 相同提及路径产生一个 `queued` 回执和一个关联至该评论 ID 的待执行 Run。 |

## 本轮证据与待验条件

- `v0.11.0` 和 `v0.11.1` 固定源码各通过三项核对，覆盖路由、Issue 范围 Run 读取、`/note` 与 `trigger_outcomes`。GitHub API 配额耗尽后，通过 SHA-256 校验的本地源码快照复验。两版评论 handler 的源文件相同。HTTP 状态、真实用例写入和排队结果待运行原生用例。
- 本机 Docker CLI 缺少可访问的 daemon socket。尝试启动一次性 Colima profile 时，现有 x86_64 构建要求缺失的 QEMU，未启动虚拟机。运行器预检返回 `2`，两版原生检查均标为 `unknown`。后续可通过 GitHub 托管工作流或有权使用的本地临时 Docker daemon 实测。测试账号及凭据由上游 fixture 和运行器生成。
- 发行镜像、真实 Daemon 的接单运行、G8 专属账号及完整 MCP 写动作清单需各自的隔离环境和观察证据。双版本原生测试的通过范围是上表五项，`queued` 对账截止于服务端 Run 创建。[任务 J 与生产验收范围](multica-backend-tasks.md)
