# Multica Backend MCP 部署、配置与升级手册

适用于维护 Vultr MCP、腾讯云 Multica 和云端 Dot 连接的人。Dot 经公网 HTTPS 进入 Vultr。Vultr 按 `instance_id` 选择实例，经 EasyTier 调腾讯云的 Multica API。工作区协调员使用 Multica 原生运行时。跨端任务的原件、结果与签收由 Task Mailbox 保存。[组件分工](../../docs/decisions/001-dot-multica-gateway.md)

| 您要做的事 | 从哪里开始 |
|---|---|
| 查看正在运行的发行、入口与服务状态 | [现网速查](#现网速查) |
| 首次在新 VPS 安装服务或接入 Dot | [首次部署](#首次部署)，按第 1–5 屏执行 |
| 换腾讯云地址、轮换 PAT、新增实例或工作区 | [维护现网配置](#维护现网配置) |
| 更新 Vultr 上的 MCP，或切回上一发行 | [升级与回退](#升级与回退) |
| 跟进一周多次的上游发版，或升级腾讯云 Web、API、数据库迁移 | [跟进上游 Multica](#跟进上游-multica) |
| 定位授权、派发和回程故障 | [故障定位](#故障定位) |

## 现网速查

2026-11-20，Vultr 的 `multica-backend.service` 已运行并启用开机启动，发行是 `0.1.0-ce2f26d619e8`。实例 `tencent` 的九项原生写能力已登记，专属账号通过真实项目、Issue 和 Run 的读取校验。公子已在云端添加 MCP。截至本次整理，目标 Dot 的工具调用结果和真实业务签收仍待原会话读回。独立恢复 timer 当日未安装。[首次上线回执](#2026-11-20-首次生产上线回执) · [工程验收记录](../../docs/multica-backend-tasks.md)

在已配置 SSH 别名的工作机执行。最后一条只输出 Multica API 地址。仓库内用示例域名，现场地址从配置取。

```sh
ssh vps-herdr 'systemctl show multica-backend.service -p ActiveState -p UnitFileState; readlink -f /opt/multica-backend/current'
ssh vps-herdr 'systemctl show multica-backend-recover.timer -p LoadState -p ActiveState'
ssh vps-herdr sudo /opt/multica-backend/enroll-pat --check
ssh vps-herdr "sudo python3 -c 'import json; print(json.load(open(\"/etc/multica-backend/config.json\"))[\"instances\"][\"tencent\"][\"origin\"])'"
```

运行中的公网基址记录在 `/etc/multica-backend/oauth.env` 的 `MULTICA_MCP_PUBLIC_BASE_URL`，Dot 连接 URL 为该值加 `/mcp`。Vultr 本机监听 `127.0.0.1:8770`。持久状态位于 `/var/lib/multica-backend/`，包括派发账本和 OAuth 状态。私有配置与凭据位于 `/etc/multica-backend/`。版本化程序位于 `/opt/multica-backend/releases/`。

## 首次部署

第 1–5 屏适用于一台新主机。已有服务直接进入现网配置或升级章节。工作机命令从仓库根目录执行。Vultr 安装和切换命令使用 Bash 的 root 终端。

## 第 1 屏 · 核对公开入口和两种身份

首次安装时实测 Vultr 使用 Python `3.14.4`、systemd `259`。ngrok 的 HTTPS 隧道指向 `headscale-ingress.service` 的 `127.0.0.1:19080`，Caddy `2.11.7` 使用 `/etc/headscale-ingress/Caddyfile`。信箱、Decision 与 Multica 的精确路由共用一个 `route`，旧 gateway 在末尾兜底。新主机先核已有路由、端口与 Caddy 启动方式。当前主机使用 `run --config`、`admin off` 和信号重载。

| 由谁操作 | 屏幕上需确认的值 |
| --- | --- |
| Vultr 入口维护者 | 从现有 ngrok 入口回读获准的 HTTPS origin。`PUBLIC_BASE` 为该 origin 加 `/multica-backend`。沿用同一域名和隧道时没有新 DNS 记录。若需改域名，域名所有者先核对 DNS、隧道绑定及证书，后续两种回调也按新地址重核。 |
| GitHub OAuth App 所有者 | 核现有 App 是否获准复用。追加 `${PUBLIC_BASE}/auth/callback` 为精确回调并保留原回调。现行 GitHub 支持同 App 最多十条回调，此拓扑无须为多一个回调而新建 App。若现有 App 不获准共享、没有可用回调额度或所有者要求独立密钥与撤销边界，则为 Multica 另建 App。无需扩大通配范围。用实际登录者的 GitHub **数字用户 ID** 做准入，认证请求为 `read:user`。 |
| Multica 实例所有者 | 确认已登记的专属 Multica 账号及其原生 `user_id`。没有专属账号才新建。为该账号签发有效期受控的 `mul_` PAT，按试点实例、工作区和项目配置原生权限，核对工作区与现任协调员 UUID。私有项目需具备实际项目资格。GitHub 登录身份和 Multica 写入主体各自独立核对。 |

GitHub 管理页上的 **Authorization callback URL** 是 GitHub 回向本 MCP 的 `${PUBLIC_BASE}/auth/callback`。ChatGPT 原生连接管理页的 redirect URI 是本 MCP 回向 ChatGPT 的另一个地址，填进 `MULTICA_MCP_ALLOWED_REDIRECT_URIS`。后者以目标连接实际显示的完整值为准，DCR 模式也需精确匹配。[GitHub 回调配置](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/creating-an-oauth-app) · [OpenAI 回调要求](https://developers.openai.com/plugins/build/auth#redirect-url) · [Multica PAT](https://multica.ai/docs/auth-tokens) · [身份 ADR](../../docs/decisions/002-identity-and-workspaces.md)

## 第 2 屏 · 构建并移交无凭据发布目录

本地从仓库根目录用 `uv` 和 Python 3.11+ 构建，路径使用新目录。脚本复制 MCP 源码和测试所需文件到临时目录，执行该快照的用例，生成 wheel、带哈希的运行依赖与 `SHA256SUMS`。已入库的 `mcp/uv.lock` 存在时使用锁定版本，否则本次对独立快照生成锁。采用主会话确认的源快照构建。

```sh
rtk proxy bash deployment/multica-backend/build-release.sh /absolute/path/to/new-release
```

由维护者将整个发布目录复制到 Vultr 的私有暂存路径。另从同一份已核源码复制 [scripts/enroll_multica_pat.py](../../scripts/enroll_multica_pat.py) 到暂存目录，供第 3 屏安装。它单独交付。保留本次发行包中的 `verify-route.py`、unit 和模板，后续换版与回退会使用。到 Vultr root 终端执行。以下以 `0.1.0-r1` 为示例，每次发行使用唯一标签。

```bash
cd /absolute/path/to/uploaded-release
RELEASE_ID=0.1.0-r1
install -d -m 0755 /opt/multica-backend/releases
bash install-release.sh "/opt/multica-backend/releases/$RELEASE_ID"
```

准备脚本校验文件哈希，在新目录创建独立 `.venv`，从 PyPI 安装与锁中哈希匹配的 wheel，并验证依赖及服务模块导入。脚本使用独立 pip 配置，不继承个人镜像与凭据。失败时该目录保留供诊断，重试使用新的发行目录。可在隔离机用同一脚本将发行装到 `/tmp` 下的新绝对路径。切换 `current`、安装 unit 和启动由第四屏执行。

## 第 3 屏 · 在 Vultr 私密终端录入配置

首次配置在上传的发行目录、Vultr root 终端执行。目录权限为 `0700`，私有文件归 `root:root`、`0600`。以下初始化命令要求配置目录尚不存在。已有安装使用后面的现网维护步骤。GitHub 凭据可复用已获准的 App，签名材料和 OAuth 状态归新服务独立持有。

```bash
(
    set -eu -o noclobber
    set +x
    umask 077
    mkdir -m 0700 /etc/multica-backend
    install -m 0600 config.example.json /etc/multica-backend/config.json
    install -m 0600 oauth.env.example /etc/multica-backend/oauth.env
    install -m 0755 enroll_multica_pat.py /opt/multica-backend/enroll-pat
    for name in github-client-id github-client-secret; do
        IFS= read -r -s -p "Enter $name: " value
        printf '\n' >&2
        test -n "$value"
        printf '%s\n' "$value" > "/etc/multica-backend/$name"
        unset value
    done
    python3 -c 'import secrets; print(secrets.token_urlsafe(32))' > /etc/multica-backend/oauth-signing-key
)
```

| 私有文件 | 必填配置与回读 |
| --- | --- |
| `oauth.env` | `MULTICA_MCP_PUBLIC_BASE_URL` 填实际 HTTPS 基址，末尾为 `/multica-backend`。`MULTICA_MCP_GITHUB_PRINCIPALS` 用 GitHub 数字用户 ID 和已获准的 scopes。生产 G8 配置为 `["read","write"]`。将目标 ChatGPT 连接显示的精确 URI 登记在 `MULTICA_MCP_ALLOWED_REDIRECT_URIS`。保持示例中 systemd 环境文件的引号格式。 |
| `config.json` | `instances` 下为已登记实例，填实际 `origin`、`expected_user_id`、`pat_credential: "multica-pat"`、`principals: ["github:<同一数字 ID>"]` 和工作区 UUID 对应的 `coordinator_id`。模板 `enabled_writes: []` 适合做只读验收。配置业务写入时填该版本工具目录中的准确动作名。EasyTier HTTP 需使用已核实的 RFC 1918 私网 IP，并显式设置 `allow_private_http: true`。 |

若新 ChatGPT 连接的专属 redirect URI 尚未生成，以团队控制的精确 loopback 测试 URI 做启动探测，例如本机测试客户端的 `http://127.0.0.1:18770/callback`。先完成下一屏的无需登录探测，再在 ChatGPT 创建原生连接，抄回该连接显示的精确 URI，用它替换测试 URI 并重启本服务，随后在同一连接做 OAuth。平台若在展示 URI 前阻断注册，保留拒绝回执，由连接管理方从该连接取值再继续。

在 Multica 专属账号的 **设置 → API Token** 生成 PAT。根据上表填好两个配置文件，再在 Vultr 的私密交互终端运行下列命令。录入工具按指定实例请求 `GET /api/me`，确认原生用户 UUID 匹配后才保存 PAT，校验结果只显示状态。

```bash
sudoedit /etc/multica-backend/config.json /etc/multica-backend/oauth.env
python3 -m json.tool /etc/multica-backend/config.json >/dev/null
/opt/multica-backend/enroll-pat --instance tencent
/opt/multica-backend/enroll-pat --instance tencent --check
```

G8 的写入同时使用 OAuth 的 `write`、实例的 `enabled_writes` 和专属账号的原生权限。建卡派发需工作区的 text 属性 `correlation_property_id`。带原 job 的派发另需不同的 text 属性 `mailbox_property_id`、准确的 `mailbox_recipient` 及获准的信箱读取身份。当前协议也核对历史 Issue 的 `metadata.task_mailbox_job_id`。若旧系统另用文本属性保存原 job，可把它的 UUID 填入 `legacy_mailbox_property_id`。每个请求沿原键对账。[MCP 服务端](../../mcp/README.md) · [集成验收](../../docs/multica-backend-tasks.md#集成任务)

回程查询获准后，在同一 `oauth.env` 加 `MULTICA_BACKEND_MAILBOX_URL` 与 `MULTICA_BACKEND_MAILBOX_SUBJECT`，向主服务与按需启用的恢复 unit 增加 `LoadCredential=mailbox-token:/etc/multica-backend/mailbox-token`，用本服务专用且已核准的信箱读取令牌及后续换证方式。包装器从 unit 凭据读取令牌。其他 Multica 实例需给运行该实例的 unit 配同名 `pat_credential`，每实例使用自己的凭据文件。

## 第 4 屏 · 启动回环服务，核验 OAuth 发现

从私有暂存发布目录执行首次安装。先确认 `8770` 无监听。`current` 初次用 `ln -s` 建立，已存在时走后文换版操作。独立 unit 用 `LoadCredential` 注入配置和 PAT，应用 OAuth 值由包装器从 unit 凭据读取。journal 和 state 按本服务保管。

```bash
read -r -p 'Verified public base ending /multica-backend: ' PUBLIC_BASE
(
    set -eu
    listeners=$(ss -H -ltn 'sport = :8770')
    test -z "$listeners"
    test ! -e /etc/systemd/system/multica-backend.service
    systemd-sysusers "$PWD/multica-backend.sysusers.conf"
    ln -sT "/opt/multica-backend/releases/$RELEASE_ID" /opt/multica-backend/current
    install -m 0644 multica-backend.service /etc/systemd/system/multica-backend.service
    systemd-analyze verify /etc/systemd/system/multica-backend.service
    systemctl daemon-reload
    systemctl start multica-backend.service
    systemctl is-active multica-backend.service
    python3 verify-route.py "$PUBLIC_BASE" --local-only
)
```

探测必须读到 `/health` 200、MCP 无认证 401、准确的 `WWW-Authenticate` 资源元数据位置、预期 issuer 和 DCR / PKCE `S256` 元数据。实际权限、令牌交换、工具发现和业务读取尚需下一屏的实际会话证据。[MCP OAuth 启动契约](../../mcp/AUTH.md) · [systemd 凭据](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html#LoadCredential=ID:PATH)

## 第 5 屏 · 公布精确路由，再授权 Dot

入口维护者获准操作共享 Caddy 后，在现有 `route` 内、旧 gateway 兜底之前插入 `caddy-route.example`。工作副本和回退副本都放在 root 可控的原配置目录。对比只增加此片段，匹配精确 MCP / OAuth 路径，保留 well-known 路径、Host、查询及 Cookie。当前共享 Caddy 未启用访问日志，若现场开过日志，先屏蔽本服务路由的访问日志以保护 OAuth 查询参数。

```bash
LIVE=/etc/headscale-ingress/Caddyfile
BEFORE=$(mktemp "$LIVE.before-multica.XXXXXXXX")
CANDIDATE=$(mktemp "$LIVE.candidate.XXXXXXXX")
cp "$LIVE" "$BEFORE"
cp -p "$LIVE" "$CANDIDATE"
sudoedit "$CANDIDATE"  # 将 caddy-route.example 的片段放入现有 route 的兜底之前
(
    set -eu
    grep -Fq '@multica_backend_oauth_metadata' "$CANDIDATE"
    cmp -s "$LIVE" "$BEFORE"  # 其他维护者已改动时，重新合并
    /usr/local/lib/headscale-ingress/caddy validate --config "$CANDIDATE" --adapter caddyfile
    mv -T -- "$CANDIDATE" "$LIVE"
    systemctl kill --kill-whom=main --signal=SIGUSR1 headscale-ingress.service
)
# 读回 Caddy 重载完成后执行探测。
python3 verify-route.py "$PUBLIC_BASE"
```

`admin off` 的当前入口用 `SIGUSR1` 读取启动时指定的配置，无须开启管理 API。发信号后读回 Caddy 的加载结果和外部探测，同时用原有只读探测核信箱、Decision 和旧 gateway。若 Caddy 配置或启动方式已有变更，先复核信号适用条件。入口验证失败按下文撤回。[Caddy 信号重载](https://caddyserver.com/docs/command-line#signals) · [Caddy route 顺序](https://caddyserver.com/docs/caddyfile/directives/route)

在目标 Dot 的 ChatGPT 连接管理页添加自定义 MCP，使用探测通过的 `${PUBLIC_BASE}/mcp`、OAuth 和 DCR。已添加的连接直接打开并用获准 GitHub 账号登录。回调匹配见第 3 屏。在目标会话选中该连接，让 Dot “只读列出实例，查每个已登记工作区的标识，并告诉我 `tencent` 下 `cloud-work` 的现任协调员”。验收时查看实际的 `list_instances`、`get_workspace` 和 `get_coordinator` 工具回执，预期协调员为 Mike。再用 `list_projects` 和已知的 Issue/Run 核对业务对象。写入试验使用指定原任务，信箱结果的精确签收由实际收件方完成。[云端插件装配](../../plugin/README.md)

## 第 6 屏 · 按需启用原请求恢复

只读试点可保持恢复定时器未安装。后续获准自动续办时，从同一发行安装 `multica-backend-recover.service` 和 `.timer`。oneshot 共享同一个 `current` venv、系统账号、实例配置与 SQLite 状态。它按当前授权处理原台账，`accepted` 可能续发，`unknown` 只核原生对象。案件从台账取得关联，未受理的信箱来件由既有流程处理。腾讯云的 Run 补报器有独立单元与职责。

```bash
(
    set -eu
    install -m 0644 multica-backend-recover.service multica-backend-recover.timer /etc/systemd/system/
    systemd-analyze verify /etc/systemd/system/multica-backend-recover.{service,timer} /etc/systemd/system/multica-backend.service
    systemctl daemon-reload
    systemctl start multica-backend-recover.service
)
systemctl show multica-backend-recover.service -p Result -p ExecMainStatus
journalctl -u multica-backend-recover.service -n 10 --no-pager
```

独立核对首轮汇总、预期原请求和实际副作用后，维护者可执行 `systemctl enable --now multica-backend-recover.timer`，用 `systemctl list-timers multica-backend-recover.timer` 查下一次计划，并读回一次自然运行。定时器在上轮完成后约一分钟触发，同一 oneshot 由 systemd 串行运行。暂停自动续办可先停用本 timer，再处理正在运行的 recovery 及在途原单。主服务须处于活动状态才能启动 recovery。

## 维护现网配置

| 变更 | 修改位置 | 生效和验收 |
|---|---|---|
| 同一套 Multica 更换 IP、域名或端口 | `/etc/multica-backend/config.json` → `instances.tencent.origin`。值为协议、主机和可选端口，例如 `https://multica.example.org`，路径留空 | 先从 Vultr 核实新主机的归属、TLS 或 EasyTier 路径，再按下方步骤验证账号和原项目。公网 MCP 的 issuer/resource 相同时，Dot 沿用现有连接 |
| 新增 VPS 或工作区 | 新的独立 Multica 设新 `instance_id`、专属 `pat_credential` 与 `expected_user_id`。同一实例只新增工作区时，在 `workspaces` 增加其 UUID、现任协调员及该工作区的关联属性 | 新凭据在主 unit 及已使用的恢复 unit 中分别加 `LoadCredential=<凭据名>:/etc/multica-backend/<凭据名>`，执行 `systemctl daemon-reload`。通过 Dot 的 `list_instances`、`get_workspace`、`get_coordinator` 查回正确实例和人员 |
| 更换公网入口或 OAuth 回调 | `/etc/multica-backend/oauth.env`、相应隧道/Caddy 路由、GitHub App 的服务回调和 Dot 连接配置。GitHub 回调为 `${PUBLIC_BASE}/auth/callback`。ChatGPT 客户端回调使用管理页显示值 | 按新公网基址重跑探针，确认 issuer、资源和注册端点，随后在目标 Dot 上完成该资源的 OAuth 登录。复用 GitHub App 时保留其他服务仍在使用的回调 |
| 调整某个写动作或信箱回程 | 改实例的 `enabled_writes` 或工作区的回程身份与关联属性 | 核对 OAuth scope、专属账号的项目及 Agent 访问权。新增授权动作按原 `request_id` 查 Issue 和实际 Run，带信箱的业务另核原 job 结果版本及读确认 |

**更换后端地址。** 在 Vultr 私密 Bash 终端先把原 `config.json` 复制到 root 专用备份目录并记下路径，再执行下列命令。若格式检查或 `--check` 失败，恢复原配置再重试。主服务只在重启时取得新的 systemd 凭据快照。

```bash
(
    set -eu
    sudoedit /etc/multica-backend/config.json
    sudo python3 -m json.tool /etc/multica-backend/config.json >/dev/null
    sudo /opt/multica-backend/enroll-pat --instance tencent --check
    sudo systemctl restart multica-backend.service
    systemctl is-active multica-backend.service
)
```

**轮换 PAT。** 在同一 Multica 专属账号生成新 PAT。在工作机执行下列命令。第一条通过 SSH 分配交互终端，输入无回显。第二条使服务重新加载 `/etc/multica-backend/multica-pat`。随后用 Dot 读取一个既有项目和指定 Run，验证成功再撤销旧 PAT。GitHub OAuth 和 MCP 签名密钥有各自的生命周期。[换证脚本](../../scripts/enroll_multica_pat.py)

```sh
ssh -t vps-herdr sudo /opt/multica-backend/enroll-pat --instance tencent --replace
ssh vps-herdr 'sudo /opt/multica-backend/enroll-pat --check && sudo systemctl restart multica-backend.service && systemctl is-active multica-backend.service'
```

## 升级与回退

**升级 Vultr MCP。** 从第 2 屏开始，先构建、验证并安装到新的 `/opt/multica-backend/releases/<发行号>`。新发行在自己的 venv 安装和执行 `pip check`，期间旧发行继续服务。保留旧发行及对应的原发布包，比较新旧 unit、代理片段和状态库兼容性。

1. 在维护窗口记录当前 `readlink -f /opt/multica-backend/current`、timer 的 active/enabled 状态及尚待确认的请求。暂停新的业务写入。如果恢复 timer 活跃，临时 `systemctl stop multica-backend-recover.timer`，等待已启动的 oneshot 完成。对已发出的请求按原键查 Multica，再停主服务。
2. 在 Vultr root 终端做一致性备份。以下命令在两种写进程均停止后执行。备份目录会包含凭据、OAuth 状态和 SQLite 账本，留在受控存储。若备份失败，保持原 `current`，用原发行恢复服务和先前活跃的 timer。

```bash
(
    set -eu
    umask 077
    if systemctl is-active --quiet multica-backend.service ||
       systemctl is-active --quiet multica-backend-recover.service; then
        echo '请先完成停写并停止服务' >&2
        exit 1
    fi
    backup_dir=$(mktemp -d /var/backups/multica-backend.XXXXXXXX)
    readlink -e /opt/multica-backend/current > "$backup_dir/previous-release"
    tar -C / -cpf "$backup_dir/config-and-state.tar" etc/multica-backend var/lib/multica-backend
    tar -tf "$backup_dir/config-and-state.tar" >/dev/null
    printf '本次备份目录 %s\n' "$backup_dir"
)
```

3. 将新 unit 或 drop-in 的变更与现状逐项合并，备份改动前的文件，验证后执行 `systemctl daemon-reload`。仅程序更新时直接切换。下面命令在**新发布包的暂存目录**执行，输入已安装的发行目录名和真实公网基址。临时链接与 `current` 在同一文件系统内原子切换。

```bash
(
    set -eu
    read -r -p '新发行目录名：' release_id
    read -r -p '公网 HTTPS 基址（末尾 /multica-backend）：' public_base
    root_dir=/opt/multica-backend
    [[ "$release_id" =~ ^[a-zA-Z0-9][a-zA-Z0-9._-]*$ ]]
    test -x "$root_dir/releases/$release_id/.venv/bin/multica-backend-mcp"
    ln -sT "$root_dir/releases/$release_id" "$root_dir/current.next"
    mv -T "$root_dir/current.next" "$root_dir/current"
    systemctl start multica-backend.service
    systemctl is-active multica-backend.service
    python3 verify-route.py "$public_base"
)
```

4. 在原 Dot 会话查 `list_instances`、`get_coordinator` 和一个已知 Issue/Run。写契约有变时，使用指定的验收任务和稳定请求 ID 核对真实副作用。恢复先前活跃的 timer 并观察一次自然执行，保存新旧发行号与验证结果。首次上线通过验收时用 `systemctl enable multica-backend.service` 开启主服务的开机启动。

**回退。** 若新版本无法启动、探针失败或原任务归属/派发语义变化，暂停写入和恢复 timer，记录已受理的请求及新版本产生的状态。在备份目录的 `previous-release` 核实旧发行路径。旧程序与现有账本兼容时，停主服务，以同样的 `ln -sT`、`mv -T` 切回旧目录。恢复配套的 unit 或配置变动后，重跑上面的服务、路由及 Dot 读取检查。若账本格式不兼容或换版期间已有新写，先保留新状态，在独立目录恢复备份并逐件对账，再决定恢复点和切换时机。入口有改动时只撤回本次 Caddy 路由，校验后按第 5 屏重载，同时核对原信箱与 Decision 路径。

## 跟进上游 Multica

上游 Web/API/Daemon 有独立版本。更新腾讯云后要核 MCP 契约。日常按以下顺序处理。

1. **发现候选。** 在仓库根目录执行 `python3 scripts/check_multica_release.py`。报告列出上游正式版、部署比较基线和各候选的官方变更链接。[发行检查工作流](../../.github/workflows/check-multica-release.yml)在默认分支且 Actions 启用时，计划每天北京时间 09:23 检查，也支持手动运行。
2. **验证影响。** 对比 [兼容清单](../../compatibility/candidate_versions.json) 和发布说明。在具备隔离 Docker 环境的工作机运行 `python3 scripts/check_multica_candidate.py --isolated`，或手动运行 [GitHub 候选版检查](../../.github/workflows/check-multica-candidate.yml)。看 JSON 的逐项结果及退出码，`2` 表示证据或前置条件不足。账号归属、跨工作区拒绝、静默评论与触发 Run 是关键回归项。源码比对、原生测试路由和实际发行镜像要分别留证。[候选版验证](../../docs/multica-backend-candidate.md)
3. **升级腾讯云。** 按[腾讯云升级手册](../../docs/tencent-upgrade.md)核镜像及 Compose，停写后备份 **Multica PG17 和上传卷**，验证可恢复后再执行目标版迁移。回切前核实数据库迁移兼容性。镜像切回无法撤销已执行的数据库迁移。Task Mailbox 使用的 win-work PostgreSQL 18.7 独立维护。
4. **从调用方复验。** 从 Vultr 核专属 PAT、项目、Issue 与 Run。从 Dot 验工具和目标对象，再按影响范围核写动作、腾讯云补报和原信箱回程。将镜像版本、适配器发行号、时间及实际通过的能力记入对应回执。2026-11-20 的记录里，腾讯云镜像为 `v0.11.0`，`v0.11.1` 为已发现的候选。[已记录的版本差距](../../docs/multica-backend-tasks.md#当前发行差距)

## 故障定位

| 现象 | 先查哪一层 | 恢复后的证据 |
|---|---|---|
| 公网 404/502 或 OAuth 发现失败 | 在 Vultr 从原发布包运行 `python3 verify-route.py "$PUBLIC_BASE" --local-only`。本机通过后查 Caddy 精确路径、Host、ngrok 和 HTTPS，再去掉 `--local-only` 重跑 | 回环 health 200，公网未认证 MCP 401，两个发现文档均 200，issuer 和资源与基址一致 |
| Dot 提示登录或回调不匹配 | 分别核 GitHub App 回向 MCP 的 `/auth/callback` 和 MCP 回向 ChatGPT 的精确 redirect URI。变更 issuer、域名或签名密钥后在目标连接重新授权 | Dot 实际发现工具，并读回 `tencent` 与工作区协调员 |
| 工具返回上游 401、403 或目标不可见 | 运行 `enroll-pat --check` 核 Multica 用户 UUID，随后核注册的工作区、私有项目资格、Agent 访问范围及允许动作 | 用同一主体成功核到原对象。其他工作区对象依旧按原生权限处理 |
| 写入超时、已建卡却缺结果 | 按原 `request_id`、原 Issue 和 Run 查派发账本，再查原 job 的结果版本及 ACK。`unknown` 保留作只读对账。恢复 timer 只处理本服务已受理的请求 | 原件、实际 Run 和结果关联可追溯。信箱不可用时原生内部任务仍可独立查询 |

## 部署前隔离验证

首轮本机隔离快照的 72 项 MCP 测试通过。发布目录校验、独立 venv 按哈希安装、包依赖检查、合成凭据启动、回环 401 与两类 OAuth 元数据、同一配置和台账的恢复入口均通过。Caddy 片段与 systemd 设定完成静态核对。

## 2026-11-20 首次生产上线回执

北京时间 `16:02:15` 读回。Vultr 的 `multica-backend.service` 为 `active`、`enabled`，监听 `127.0.0.1:8770`。当前发行 `0.1.0-ce2f26d619e8` 使用主线冻结快照，包含 `list_issues`、原派发标记读回及 Gateway 的最新变更。该快照通过 82 项 MCP 测试。Vultr 校验发布文件哈希、独立 venv 安装、依赖和 unit 通过。

- 回环 `/health` 为 `200`，公网 `/multica-backend/mcp` 对无凭据请求为 `401`。受保护资源和签发方发现各返回 `200`，挑战、资源受众、issuer、DCR 入口及 PKCE `S256` 匹配。
- Caddy 候选配置验证通过，以 `SIGUSR1` 装入新增精确路由。Task Mailbox、Decision Service 和旧 MCP 在回环及公网的上线前后探测状态一致，三个既有进程 PID 未变。原配置保存在 Vultr 上的 `/etc/headscale-ingress/Caddyfile.before-multica.x8l_e_zw`，由 root 持有，权限 `0600`。
- 新进程启动时使用主线提供的私有配置。自动恢复 timer 未安装。目标 Dot 的 OAuth 登录、工具发现与实际业务调用另行取证。

同日后续，公子确认云端 MCP 已添加。目标 Dot 会话的首笔只读回执按第 5 屏核对。
