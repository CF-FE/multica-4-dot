# Multica Backend MCP 服务端

`multica_backend/` 存放服务端 Python 代码。云端 Dot 的插件素材在 [plugin/](../plugin/)，工作区协调员使用的 CLI/REST 指南在 [multica-backend Skill](../skills/multica-backend/SKILL.md)。服务架构与进度见[决策索引](../docs/backend-integration.md)及[交付表](../docs/multica-backend-tasks.md)。

| 模块 | 用途 |
|---|---|
| [multica_api.py](multica_backend/multica_api.py) | 绑定服务端配置的实例、调用身份与目标范围，核对原生项目、Issue 和指定 Run 的读取契约 |
| [delivery.py](multica_backend/delivery.py) · [原生派发](multica_backend/native_dispatch.py) | 在 SQLite 中认领稳定请求，以一次原生请求同事务写入关联属性，超时后回查 |
| [服务入口](multica_backend/server.py) · [Gateway](multica_backend/gateway.py) | OAuth、Streamable HTTP 工具发现、实例目录、项目/Run 读取、稳定请求与操作结果 |
| [业务操作](multica_backend/native_operations.py) · [信箱适配](multica_backend/mailbox.py) | 工作区及负责人、项目、Issue、静默备注、定向引导、复审、取消/重跑与原 job 结果的关联 |

## 单笔信箱接单

`get_dispatch_acceptance` 是按原请求的只读查询，接受 `instance_id`、`workspace_id`、`project_id`、`request_id` 和 `job_id`。它回显冻结的 job、摘要、协调员与原卡，返回原生接单备注和 Run 启动证据。新卡的 Run 以服务端记录的备注 `source_task_id` 定位，并单独核验原生 `started_at`。缺少绑定的 Run 只作候选，历史卡沿原操作回执对账。缺少可验证接单回执时返回 `unconfirmed` 及原因，有可靠线索时附历史卡 ID。`get_dispatch` 继续查询派发账本，`get_dispatch_result` 继续查询结果及已读 ACK。协调员写备注及 G8 对账见 [工作区协调员 Skill](../skills/workspace-coordination/SKILL.md#g8-经信箱交给工作区协调员)。

恢复沿原授权身份和原 SQLite 文件办理。发现历史候选卡后，该请求只能对账。以前已确认的记录若缺少冻结的协调员，原查询仍可用。仍具备原权限时，可用完全相同的派发参数重放以补存该身份，确认记录直接读回。上线前需要独立的 Task Mailbox 只读授权，以及协调员本人通过原生身份读取和回复该件的权限。

## 实例地址、授权与换证

实例目录由服务端的 `MULTICA_MCP_CONFIG` 指向，systemd 从 Vultr 私有的 `/etc/multica-backend/config.json` 提供快照。`instances.<实例标识>.origin` 是 **Multica API 的 origin**，形如 `https://multica.example.org`，不带 `/api` 或自定义路径。工作区在所属实例的 `workspaces` 下登记。云端工具只接受 `instance_id`；将同一实例迁到另一个地址时修改 `origin`，核实专属账号与工作区在该实例的对应关系，然后重启本服务并读回。自托管 HTTP 私网只在固定内网 IP 和已核实的加密 overlay 上显式启用 `allow_private_http`。若是另一套独立实例，新增实例标识和独立凭据。云端的公网入口及 GitHub 服务回调由 `MULTICA_MCP_PUBLIC_BASE_URL` 单独配置。[配置样例](../deployment/multica-backend/config.example.json) · [OAuth 路由](AUTH.md)

在 Vultr 上执行 `sudo /opt/multica-backend/enroll-pat --replace`，无回显输入新的 Multica PAT。脚本先通过当前实例的 `/api/me` 对比预期用户 UUID，再原子替换配置指向的凭据文件。默认实例为 `tencent`，默认凭据源文件为 `/etc/multica-backend/multica-pat`。原服务在运行时执行 `sudo systemctl restart multica-backend.service`，使 systemd 加载新凭据；核读后可在 Multica 撤销旧 PAT。[换证工具源码](../scripts/enroll_multica_pat.py)

在仓库根目录运行以下命令。服务端测试使用已安装 `./mcp[test]` 的 Python 3.11+ 独立环境；仓库级测试覆盖补报、读取及发行检查。

```sh
PYTHONPATH=mcp python3 -B -m unittest discover -s mcp/tests -q
python3 -B -m unittest discover -s tests -q
```

版本更新时可运行[发行检查](../scripts/check_multica_release.py)，再按[只读契约检查器](../scripts/check_multica_contract.py)和[候选版演练](../docs/multica-backend-candidate.md)取证。启动、打包和恢复步骤见[部署手册](../deployment/multica-backend/README.md)。真实云端 OAuth、写入和原件签收须分别核对原生回执。
