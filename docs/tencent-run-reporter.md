# 腾讯云 Multica Run 终态补报

补报器每分钟检查已登记的具体 Run。发现 `failed`、`cancelled` 或 `completed` 时，它向 Task Mailbox 的原任务时间线写入一条带原生证据的 `task/activity`。协调员可据此回查交付物，再沿原 job 发布结果。[汇报约定](workflow-reporting.md) · [采纳的 ADR](https://github.com/CF-FE/task-mailbox-mcp/blob/main/docs/decisions/001-task-collaboration-platform.md)

## 本轮试点与实测

| 对象 | 2026-11-20 北京时间核验 |
|---|---|
| 来源 | 已核对授权试点的工作区、项目、Issue 和唯一登记的 Run。实际绑定写在腾讯云的私有配置中。 |
| 原生 Run | 操作者通过正式 Issue 和 Run 查询核对归属。目标 Run 的平台终态为 `completed`，结束于 11:39:54。 |
| 信箱绑定 | 原 job 的 `payload.origin_task_id` 等于该 Issue UUID，且没有 `tracking`。本次显式登记该值作观测 `task_id`，使用试点的 Multica 项目 UUID 作独立的信箱观测项目。 |
| 信箱写端 | Vultr 新来源只绑定试点项目、实体 `task` 和权威 `native_observation`。专用随机 bearer 在腾讯云产生，签发端只持摘要。写端重启后健康检查通过，既有查看授权未增加。 |
| 腾讯云 | Python 3.14.4、systemd 259。定时器已启用。补报服务使用 `multica-reporter` 专用账户，读取入口使用非 root 容器并仅发布到宿主机回环。实际服务身份验证两条 GET 正常。匿名与错误凭据返回 401，错误工作区、无该项目归属与未登记的 Issue、越界路径返回 404，POST 返回 405。读取容器重启后，同一原生 Run 仍可读取。 |
| 隔离验证 | 此前 11 项补报测试通过本机与腾讯云服务身份验证。本次本机共通过 14 项测试，新增覆盖读取路由、身份和错误边界。腾讯云测试运行在独立网络命名空间，通过真实回环 HTTPS 和新 Python 进程运行已安装程序。接收方使用合同夹具。它实测服务端收件后断开、客户端重启、精确回执恢复，及重复提交只留一件。把夹具产生的完整原报文提交给 Vultr 已部署代码的 DTO，字段校验通过。 |
| 生产投递 | 14:07:57 定时器首次自然触发，信箱于 14:08:04.150721 持久化，补报器于 14:08:05 收到水位 278 的回执。同源 HTTPS GET 逐字段匹配本机回执。14:09:07 下一自然周期成功结束，收件端按来源复查仍只有 1 条事件和 1 个批次。Run 引用、事件原文、批次与完整回执保存在腾讯云私有 SQLite 台账。此次线上样本的原生终态为 `completed`，失败路径覆盖于隔离测试。 |

### 同次切换的旧来源

签发端保留旧桥的来源记录，撤销其唯一 HTTP bearer 摘要。该来源只绑定原项目的 `role/source` 原生观测，无 MCP 登录、执行绑定或工作流作者依赖。归档配置引用桥目录内的专属凭据。远端 238 条历史均来自 Mac hook 或桥运行探测，其中 233 个 hook 事件 ID 与本机归档逐项匹配。另 4 条为同类历史 hook，1 条为桥探测。

写端再次启动后，在签发端核对旧摘要已从所有授权移除，旧来源的 238 条观测仍在，其他来源及查看者策略与变更前逐项相同。腾讯云以新凭据重查得精确的信箱缺批次响应。此次核验使用签发端的策略及历史记录，封存的旧 bearer 全程留在原处。

## 数据与恢复

每个服务实例绑定一组来源和信箱端点、一个工作区及一对项目。登记每个 Issue UUID、Run UUID、信箱任务 ID，可选原 job ID。请求带 `X-Workspace-ID` 和该端点自己的 bearer。程序先取 `GET /api/issues/{issue}` 核对 Issue、工作区及项目，再取 `GET /api/issues/{issue}/task-runs?scope=issue&view=timeline`。v0.11.0 官方 API 在此返回同一 Issue 可见的历史数组。试点的本机读取入口按同一响应形状只提供服务端登记的 Run。补报器用完整 UUID 匹配唯一一行，并复核其工作区、Issue 与可见性。源端超时、未找到、范围不符或响应过大时记录诊断，本轮不产生运行事实。其他绑定照常处理。[正式查询实现](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/internal/handler/daemon.go#L6420-L6585)

对外发送原生状态、发生与观察时间、Issue 与 Run 引用。若失败记录包含错误，则附对应字段的原文引用。备注、错误正文、结果正文和附件留在 Multica。原 job 关联来自登记，证据类型标为 `registered_mailbox_job`。终态时间为空时保留空值。

SQLite 在首次外发之前提交完整报文字节、原关联、稳定批次及事件 ID。每次投递先用同一 bearer GET 原批次，仅当收到信箱领域的精确缺批次回执，才 POST 保存的原件。接收方返回 `persisted: true`、同源、同批次且精确覆盖唯一原事件时，程序在本机保存完整回执。已确认的 Run 停止轮询。已入队的原件在源端不可达时也能单独恢复投递。[信箱事务与判重](https://github.com/CF-FE/task-mailbox-mcp/blob/main/platform_service/observations.py) · [批次及回执模型](https://github.com/CF-FE/task-mailbox-mcp/blob/main/platform_service/models.py)

代理 404、权限拒绝、协议不符和传输中断都会留下原件。只有 `409 OBSERVATION_CONFLICT` 隔离该件，后续定时运行会持续报出冲突并跳过投递。交协调员凭保存的原文和原 ID 对账。其他已登记件继续处理。移除某个登记会暂停该件的查询及待发投递，按原映射加回后继续。改动已落盘 Run 的收件关联会报错。返工登记新 Run UUID。

## 服务与凭据

运行时使用 Python 3.11+ 标准库。先从仓库目录安装程序及 unit。以下为首次安装命令，在 Linux 上运行。

```sh
sudo install -Dm0644 deployment/multica-run-reporter.sysusers.conf /etc/sysusers.d/multica-run-reporter.conf
sudo systemd-sysusers /etc/sysusers.d/multica-run-reporter.conf
sudo install -Dm0644 reporter/run_reporter.py /usr/local/lib/multica-run-reporter/run_reporter.py
sudo install -d -m0750 -o root -g multica-reporter /etc/multica-run-reporter
sudo install -m0644 deployment/multica-run-reporter.service deployment/multica-run-reporter.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemd-analyze verify multica-run-reporter.service multica-run-reporter.timer
```

以[登记示例](../deployment/multica-run-reporter.config.example.json)准备私有 `/etc/multica-run-reporter/config.json`，将示例信箱地址换为所有者核准的真实 HTTPS 路径，将 `multica_origin` 指向可强制项目只读的入口。配置使用 `root:multica-reporter 0640`。两枚凭据分别存入同目录的 `multica.token` 和 `mailbox.token`，以 `root:root 0600` 保存，由 systemd `LoadCredential` 在执行时提供。首次配置已有落盘数据时校验其来源、端点、项目及登记与原件一致。

## 项目限定的本机读取入口

Multica v0.11.0 的普通账号 PAT 继承账号权限，workspace member 仍能创建和修改 Issue。临时 Run token 绑定一次运行，插件的 `tasks:read` 路由只提供消息。此次采用 PG17 受限视图直接读取 Multica 的权威记录。 [账号与任务令牌](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/apps/docs/content/docs/auth-tokens.zh.mdx) · [成员权限](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/apps/docs/content/docs/members-roles.zh.mdx) · [插件路由](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/server/pkg/publicapi/v1/routes.go#L58-L68)

- 视图由无登录的 `multica_report_view_owner` 持有。该角色只获得所需底表列的 SELECT。每次读取校验当前 Issue 所属 workspace 和项目、登记的 Issue/Run 对，以及 Run 的 agent workspace。Run 视图复用固定版本的终态历史可见规则，排除未执行的特定升级回退记录。登录账号 `multica_report_reader` 只获得两张 `security_barrier` 视图的 SELECT，无底表或登记表权限，也无业务角色成员资格。用实际数据库账号验证 SELECT 底表及修改登记与业务数据均被拒绝。 [数据库投影](../deployment/run-reader/projection.sql) · [PostgreSQL 17 视图](https://www.postgresql.org/docs/17/sql-createview.html)
- 读取容器使用 Python 标准库和 PostgreSQL 自带的 `psql`，通过现有 Docker 网络的 `postgres` 名称连接，只在宿主机回环提供 HTTP。两条 GET 均要求专用 bearer 和正确的 `X-Workspace-ID`。Issue 仅返回 ID、工作区和项目。Run 仅返回 ID、所属 Issue 和工作区、状态、完成时间及错误是否存在。实际部署用官方 API 对照了试点 UUID、归属、状态、完成时间。视图保留 PostgreSQL 的小数秒，v0.11.0 的 HTTP 表示保留到秒。 [读取入口](../deployment/run-reader/run_reader.py) · [部署定义](../deployment/run-reader/compose.yaml)

首次部署由数据库所有者通过 `psql` 执行 `projection.sql`，传入 `workspace_id`、`project_id` 和专用数据库密码的 `reader_verifier`。用受控 stdin 提供 SCRAM verifier。数据库凭据放入 `/etc/multica-run-reader/pgpass`。读取容器仅接收本机 HTTP bearer 的摘要 `http.sha256`，摘要按完整 `Authorization` 值（含 `Bearer ` 前缀）计算。两个文件均置于宿主机 root 独占的目录，由 Compose 单文件只读挂载，容器 UID 65532 可读。HTTP bearer 原文只交给 systemd 补报服务。 [PostgreSQL 17 psql](https://www.postgresql.org/docs/17/app-psql.html)

把 `deployment/run-reader` 的四个文件安装到宿主机私有部署目录，从该目录执行 `sudo docker compose -p multica-run-reader up -d --build`。使用已核准的 PG17 基础镜像，可通过 `POSTGRES_IMAGE` 固定本机镜像版本。签名 Debian 包构建可经 `DEBIAN_MIRROR` 使用云主机镜像源。首次启动成功后把补报器 `multica_origin` 指向该回环端口。优先启动 timer 并观察其首次自然调度。

### 登记、撤销与升级

- 新登记由同一组原生 ID 贯通两处。用官方 API 核同一 workspace/project 内的 Issue UUID 和完整 Run UUID。由数据库所有者向 `run_reporter.registrations(issue_id, run_id)` 写入同一对 ID，再把这对 ID 和已核的信箱 `task_id`、可选 `job_id` 一起加入补报 `watches`。以专用身份 GET 核对两处后恢复巡检。新的重跑登记新的 Run UUID。
- 撤销时先停止 timer 与在途 oneshot。若已产生待发或回执不明的批次，先按原批次 GET 对账并记录；需要阻止未发件时保留原 SQLite 行，从 `watches` 移除这对 ID，同时由数据库所有者删除对应的视图登记，最后恢复其余巡检。单独删视图登记只影响源查询，已经落盘的待发件由 `watches` 控制。信箱已接收的事实继续留在台账和信箱。
- Multica 升级前暂停补报，保存 SQLite，在目标版本检查 `issue`、`project`、`agent`、`agent_task_queue` 的列、归属关系和官方 Run 历史的可见规则。视图依赖可能影响字段删除或类型变更，先在维护环境试跑数据库迁移。若字段或语义变化，更新投影后以少量登记件对照官方 API 的 ID、范围、状态和时间，并重验拒绝用例。若需拆除 Multica 的 Docker 网络，先停止并移除读取容器，再随网络恢复。核对投影和同源回执后恢复 timer。

## 信箱与生产核验

**信箱所有者**在 Vultr 的 `TASK_PLATFORM_ACCESS_FILE` 按前述最小范围登记专用来源和 `token_sha256`。该身份只使用 HTTP 来源认证，项目查看权按收件方原授权办理。策略由写端在进程启动时加载。[授权实现](https://github.com/CF-FE/task-mailbox-mcp/blob/main/platform_service/access.py)

读取授权到位后，启用 timer，观察首次自然触发并核对原件与回执。默认轮询间隔为前一轮结束后一分钟。服务账户无登录 shell，unit 的 capability 集合为空；可写持久目录为 `/var/lib/multica-run-reporter`，权限 `0700`。

```sh
sudo systemctl enable --now multica-run-reporter.timer
sudo journalctl -u multica-run-reporter.service -n 20 --no-pager
sudo -u multica-reporter python3 - <<'PY'
from pathlib import Path
import json, sqlite3
db = Path('/var/lib/multica-run-reporter/state.sqlite3')
with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as conn:
    for run_id, raw, receipt, conflict in conn.execute('SELECT run_id,original,receipt,conflict FROM outbox'):
        batch = json.loads(raw)
        print(run_id, batch['batch_id'], batch['events'][0]['event_id'],
              json.loads(receipt) if receipt else conflict or 'pending')
PY
```

暂停用 `sudo systemctl disable --now multica-run-reporter.timer`，再用 `sudo systemctl stop multica-run-reporter.service` 停止在途扫描。保留数据库，恢复后能沿原 ID 对账。开发验证运行 `python3 -B -m unittest discover -s tests -v`，测试使用系统 OpenSSL 创建一次性回环证书。
