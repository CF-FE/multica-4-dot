# Vultr 部署 Multica Backend MCP

2026-11-20。此目录提供可构建、可隔离演练的发布素材。以下各屏是取得生产授权后的操作顺序。首轮只读，使用现有 HTTPS 入口与 GitHub OAuth。核对角色、上游版本或连通性有缺口时，停在对应一屏。

## 第 1 屏 · 核对公开入口和两种身份

Vultr 只读盘点确认 Python `3.14.4`、systemd `259`。ngrok 的 HTTPS 隧道指向现有 `headscale-ingress.service` 的 `127.0.0.1:19080`，Caddy `2.11.7` 使用 `/etc/headscale-ingress/Caddyfile`，现有信箱与 Decision 路由在同一 `route` 内，旧 gateway 在末尾兜底。`8765–8768` 有回环监听，`8770` 当时空闲。Caddy 以 `run --config` 运行，`admin off`，没有 systemd reload 单元接口。活动配置未见 `/multica-backend`。应用和入口的权限及事实在最终安装前按当时状态复核。

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

获准后由维护者将整个发布目录复制到 Vultr 的私有暂存路径。到 Vultr root 终端执行。以下以 `0.1.0-r1` 为发行标签示例，使用本次评审实际选定的唯一标签。

```bash
cd /absolute/path/to/uploaded-release
RELEASE_ID=0.1.0-r1
install -d -m 0755 /opt/multica-backend/releases
bash install-release.sh "/opt/multica-backend/releases/$RELEASE_ID"
```

准备脚本校验文件哈希，在新目录创建独立 `.venv`，从 PyPI 安装与锁中哈希匹配的 wheel，并验证依赖及服务模块导入。脚本使用独立 pip 配置，不继承个人镜像与凭据。失败时该目录保留供诊断，重试使用新的发行目录。可在隔离机用同一脚本将发行装到 `/tmp` 下的新绝对路径。切换 `current`、安装 unit 和启动由第四屏执行。

## 第 3 屏 · 在 Vultr 私密终端录入配置

首次配置在 root 终端执行。GitHub client ID、secret 与 Multica PAT 从获准保管位置通过无回显输入录入，签名材料由 Vultr 本地生成。终端录制及 shell tracing 应关闭。只读试点的密钥和私有 JSON 文件归 `root:root`、`0600`，目录为 `0700`。已有目录中的真实配置按变更流程保存和编辑。

```bash
(
    set -eu -o noclobber
    set +x
    umask 077
    mkdir -m 0700 /etc/multica-backend
    install -m 0600 config.example.json /etc/multica-backend/config.json
    install -m 0600 oauth.env.example /etc/multica-backend/oauth.env
    for name in github-client-id github-client-secret multica-pat; do
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
| `oauth.env` | `MULTICA_MCP_PUBLIC_BASE_URL=$PUBLIC_BASE`（填实际字符串），`MULTICA_MCP_GITHUB_PRINCIPALS` 用获准的数字 ID 和 `scopes` 为 `['read']` 的政策（实际 JSON 用双引号），`MULTICA_MCP_ALLOWED_REDIRECT_URIS` 用 ChatGPT 连接管理页显示的精确 URI。JSON 值外层保留样例的 shell 单引号。 |
| `config.json` | `instances` 下为已登记实例，填实际固定 `origin`、专属账号 UUID、`pat_credential: "multica-pat"`、`principals: ["github:<同一数字 ID>"]`，以及实际工作区 UUID → 当前 `coordinator_id`。读取试点保留 `enabled_writes: []`。若经核验在 EasyTier 加密私网使用 `http://`，按当前适配器支持的私网字面地址配置并显式设 `allow_private_http: true`。 |

若新 ChatGPT 连接的专属 redirect URI 尚未生成，以团队控制的精确 loopback 测试 URI 做启动探测，例如本机测试客户端的 `http://127.0.0.1:18770/callback`。先完成下一屏的无需登录探测，再在 ChatGPT 创建原生连接，抄回该连接显示的精确 URI，用它替换测试 URI 并重启本服务，随后在同一连接做 OAuth。平台若在展示 URI 前阻断注册，保留拒绝回执，由连接管理方从该连接取值再继续。

从 Vultr 私密终端直接对已登记上游执行 `GET /api/me`，将 `multica-pat` 通过 stdin 交给 curl，检查返回 `id` 与 `expected_user_id` 精确一致。命令从配置读 origin，不在输出中打印地址、响应正文或令牌。以下 `tencent` 与登记表的实例键匹配。

```bash
(
    set -euo pipefail
    set +x
    cd /etc/multica-backend
    multica_origin=$(python3 -c 'import json; print(json.load(open("config.json"))["instances"]["tencent"]["origin"].rstrip("/"))')
    printf 'header = "Authorization: Bearer %s"\n' "$(cat multica-pat)" |
        curl -q --config - --proto '=https,http' --silent --show-error --fail --max-time 10 "$multica_origin/api/me" |
        python3 -c 'import json, sys; expected = json.load(open("config.json"))["instances"]["tencent"]["expected_user_id"]; sys.exit(None if json.load(sys.stdin)["id"] == expected else "Multica user ID mismatch")'
)
```

启用业务写入属于后续授权。派发需可用的 `correlation_property_id`，带原 job 的派发另需不同的 `mailbox_property_id`、准确的 `mailbox_recipient` 和受权的信箱读取身份。先核读两个实际工作区属性及用途，已有业务字段交其所有者保管。已知旧卡用单独文本属性保存原始 `job_id` 时，可把第三项不同的 UUID 填入 `legacy_mailbox_property_id`，供旧标记只读防重。没有证据的旧 Issue 沿原卡交接核对。具体配置及能力证据见 [MCP 服务端](../../mcp/README.md)和[集成验收](../../docs/multica-backend-tasks.md#集成任务)。

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
# 维护者在 CANDIDATE 的现有 route 中插入 caddy-route.example。
(
    set -eu
    /usr/local/lib/headscale-ingress/caddy validate --config "$CANDIDATE" --adapter caddyfile
    mv -T -- "$CANDIDATE" "$LIVE"
    systemctl kill --kill-whom=main --signal=SIGUSR1 headscale-ingress.service
)
# 读回 Caddy 重载完成后执行探测。
python3 verify-route.py "$PUBLIC_BASE"
```

`admin off` 的当前入口用 `SIGUSR1` 读取启动时指定的配置，无须开启管理 API。发信号后读回 Caddy 的加载结果和外部探测，同时用原有只读探测核信箱、Decision 和旧 gateway。若 Caddy 配置或启动方式已有变更，先复核信号适用条件。入口验证失败按下文撤回。[Caddy 信号重载](https://caddyserver.com/docs/command-line#signals) · [Caddy route 顺序](https://caddyserver.com/docs/caddyfile/directives/route)

公子在 ChatGPT 网页打开 **插件 → ＋ → 添加自定义 MCP 服务器**，填探测通过的 `${PUBLIC_BASE}/mcp`，选 OAuth，使用部署方已验证的 DCR，选择 **创建为插件**。如有待填的 ChatGPT redirect URI，完成第三屏的精确匹配后，在同一连接亲自登录获准 GitHub 账号。维护者记录原生 App、当前发行及绑定，按[插件素材](../../plugin/README.md)加挂 Skill。目标 Dot 会话显式选择插件，核实际工具清单，先用 `list_instances`、`get_workspace`、`list_projects` 和 `get_coordinator` 查目标范围与任职，再用 `get_project`、`get_issue`、`list_issue_runs` 和 `get_run` 核实原件。用隔离实例的两个项目和越界样本做验收，调用方和返回范围均要读回。单独获准的写入试验才使用生产写能力。需要原信箱签收时由实际收件的 Dot 办理。

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

## 换版与回退

- 验证通过后再由维护者启用开机自启 `systemctl enable multica-backend.service`。换版前若已启用恢复，先停 timer，等在途 recovery 结束并核原请求，再停本服务。保存专用 `/var/lib/multica-backend` 与 `/etc/multica-backend` 的受限备份。两个目录包含派发台账、OAuth 状态和凭据，保存在授权私有位置。独立状态目录和签名材料沿同一服务继续使用。
- 换版以 `ln -s "/opt/multica-backend/releases/$RELEASE_ID" /opt/multica-backend/current.next` 和 `mv -T /opt/multica-backend/current.next /opt/multica-backend/current` 切换。启动后重跑回环、HTTPS 和 Dot 只读探测。配套 unit 没改时沿用原 unit。回切旧发行前核 SQLite 兼容与在途请求，避免覆盖更新后已受理的请求。
- 首次入口验证失败，入口维护者核对共享配置自备份以来的改动，撤回本次路由，验证候选后按同一 `SIGUSR1` 路径恢复，复核原路由，再停用本服务。安装的发行和状态可保留取证。若本服务曾启用写入，交原执行方按同一 `request_id` 核完在途 Issue / Run 与回程，再切回原生操作。
