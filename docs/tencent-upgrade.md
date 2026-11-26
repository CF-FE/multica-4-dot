# 腾讯云 Multica 升级手册

适用于腾讯云 VPS `/opt/multica` 的已有实例。使用 Compose project `multica`，组合官方 `docker-compose.selfhost.yml` 与本机 `docker-compose.easytier.yml`。应用更新分别重建 `backend`、`frontend`，数据库沿用 `pgvector/pgvector:pg17` 和现有两个卷 `multica_pgdata`、`multica_backend_uploads`。本手册以 2026-11-19 的 v0.10.0 → v0.11.0 升级为例。未来升级先核对应版本的发布说明、Compose 和数据库迁移。 [官方 v0.11.0 Compose](https://github.com/multica-ai/multica/blob/cb190810a659c1a61c4a86d9f6ecfc9df4b086d8/docker-compose.selfhost.yml) · [发布说明](https://github.com/multica-ai/multica/releases/tag/v0.11.0)

日常升级按[项目升级规范](../AGENTS.md#multica-升级规范)准备目标 tag 和镜像，再在腾讯云运行 `sudo /opt/upgrade-multica.sh "$target_tag"`。脚本执行在途检查、备份、隔离迁移演练、应用切换和健康检查。现网版本以[最新升级回执](#升级回执)和容器读回为准。

## 部署约定

| 项目 | 本实例约定 |
|---|---|
| 配置文件 | `.env` 属主 `root:root`、权限 `0600`，已有密钥持续使用 |
| 网络 | 官方环回绑定与已核对的 EasyTier 私网端口 override 一起加载，访问 URL 由现有配置决定 |
| 运行数据 | PostgreSQL 与上传卷保持原映射，应用升级独立于 PG 主版本迁移 |
| 版本 | 源码 tag、运行中镜像和 `.env` 的标签分别核对，预先 checkout 新源码不会更新运行中的容器 |
| 历史来源 | v0.9.0、v0.10.0 的应用镜像使用官方 `ghcr.io/multica-ai/multica-backend` 和 `ghcr.io/multica-ai/multica-web` |

下文命令在 VPS 的 Bash root shell 中执行，各代码块复用同一会话的变量。现有 SSH 运维身份可用 `sudo -i` 进入，随后执行 `bash`。进入维护窗口前，确认在途任务已经完成或得到明确处置，并暂停新的派发与业务写入。配置模型、数据库、附件和日志保存到 VPS 私有备份目录，回报只使用脱敏字段。

## 1. 核对当前状态并准备目标版本

```bash
set +x
set -Eeuo pipefail
umask 077

deploy_dir=/opt/multica
previous_tag=v0.10.0
target_tag=v0.11.0
expected_target_commit=cb190810a659c1a61c4a86d9f6ecfc9df4b086d8
backup_dir="/var/backups/multica/${previous_tag}-before-${target_tag}-$(date -u +%Y%m%dT%H%M%SZ)"

cd "$deploy_dir"
test "$(id -u)" -eq 0
repo_owner=$(stat -c '%U' "$deploy_dir/.git")
repo_git() { sudo -H -u "$repo_owner" -- git -C "$deploy_dir" "$@"; }
test "$(stat -c '%u:%g:%a' .env)" = '0:0:600'
docker compose version
repo_git remote get-url origin
repo_git status --short
repo_git rev-parse HEAD
df -h . /var/backups
free -h

unset COMPOSE_FILE COMPOSE_PROJECT_NAME MULTICA_IMAGE_TAG
compose=(docker compose --project-directory "$deploy_dir" --env-file "$deploy_dir/.env"
  -p multica -f "$deploy_dir/docker-compose.selfhost.yml"
  -f "$deploy_dir/docker-compose.easytier.yml")

"${compose[@]}" config --quiet
"${compose[@]}" ps
docker volume inspect multica_pgdata multica_backend_uploads --format '{{.Name}}'

backend_id=$("${compose[@]}" ps -q backend)
frontend_id=$("${compose[@]}" ps -q frontend)
postgres_id=$("${compose[@]}" ps -q postgres)
test -n "$backend_id"
test -n "$frontend_id"
test -n "$postgres_id"
docker inspect --format '{{.Name}} {{.Config.Image}} {{.Image}} {{.State.Status}}' \
  "$backend_id" "$frontend_id" "$postgres_id"
docker inspect --format '{{.Name}} {{range .Mounts}}{{if eq .Type "volume"}}{{.Name}} -> {{.Destination}} {{end}}{{end}}' \
  "$backend_id" "$postgres_id"
```

核对 origin 为官方仓库、正在运行的应用标签与 `previous_tag` 一致，且两个卷确实挂在该实例。Git 操作通过 `repo_git` 以仓库属主身份运行，本实例属主为 `ubuntu`。已知的本地 EasyTier override 可保留在工作区。其他未核实的文件或修改先查清来源。磁盘需容纳备份、两套应用镜像和恢复演练所需空间。

先保护运行中版本对应的官方 Compose 和当前私网配置，再切换源码。若源码已在目标 tag，仍记录其 commit 与运行中版本的差别。下面的 `config.before.json` 含展开后的环境变量，只保存在权限受限的备份目录。

```bash
install -d -m 700 "$backup_dir"
install -m 600 .env "$backup_dir/deployment.env"
install -m 600 docker-compose.easytier.yml "$backup_dir/docker-compose.easytier.yml"
if ! repo_git show-ref --verify --quiet "refs/tags/$previous_tag"; then
  repo_git fetch --no-tags origin "refs/tags/$previous_tag:refs/tags/$previous_tag"
fi
repo_git show "${previous_tag}:docker-compose.selfhost.yml" > "$backup_dir/docker-compose.selfhost.yml"
cp docker-compose.selfhost.yml "$backup_dir/checked-out-selfhost.yml"
repo_git rev-parse HEAD > "$backup_dir/source-before.commit"
old_compose=(docker compose --project-directory "$deploy_dir" --env-file "$backup_dir/deployment.env"
  -p multica -f "$backup_dir/docker-compose.selfhost.yml"
  -f "$backup_dir/docker-compose.easytier.yml")
MULTICA_IMAGE_TAG="$previous_tag" "${old_compose[@]}" config --format json > "$backup_dir/config.before.json"

repo_git diff --quiet
repo_git diff --cached --quiet
if ! repo_git show-ref --verify --quiet "refs/tags/$target_tag"; then
  repo_git fetch --no-tags origin "refs/tags/$target_tag:refs/tags/$target_tag"
fi
target_commit=$(repo_git rev-parse "refs/tags/$target_tag^{commit}")
test "$target_commit" = "$expected_target_commit"
repo_git switch --detach "$target_commit"

MULTICA_IMAGE_TAG="$target_tag" "${compose[@]}" config --format json > "$backup_dir/config.target.json"
python3 - "$backup_dir/config.before.json" "$backup_dir/config.target.json" "$backend_id" "$frontend_id" <<'PY'
import json
import subprocess
import sys

before, target = (json.load(open(p)) for p in sys.argv[1:3])
assert before["name"] == target["name"] == "multica"
assert before["services"]["postgres"] == target["services"]["postgres"], "核对数据库配置差异后再继续"
assert before["volumes"] == target["volumes"], "核对持久卷差异后再继续"
for name, container_id, container_port in zip(("backend", "frontend"), sys.argv[3:], (8080, 3000)):
    old, new = before["services"][name], target["services"][name]
    assert old.get("ports") == new.get("ports"), f"核对 {name} 端口差异后再继续"
    assert old.get("volumes") == new.get("volumes"), f"核对 {name} 卷差异后再继续"
    expected = {(p["host_ip"], str(p["published"])) for p in old["ports"] if p["target"] == container_port}
    ports = json.loads(subprocess.check_output(["docker", "inspect", "--format", "{{json .NetworkSettings.Ports}}", container_id]))
    actual = {(p["HostIp"], p["HostPort"]) for p in ports[f"{container_port}/tcp"]}
    assert expected == actual, f"运行中 {name} 的绑定与旧版本基线不一致"
    print(name, new["image"])
PY
```

继续核对目标模型中的应用环境差异，保留既有访问地址、密钥和存储配置。模型检查只打印镜像名。未来版本的配置变化应在维护前审阅，并适配对应检查。

本次两个 v0.11.0 镜像已预置。未来若缺少镜像，在准备阶段从官方 GHCR 显式获取指定平台，或在可信机器 `docker save` 后搬运并 `docker load`。准备完成后核对目标配置实际引用的每个镜像均存在，且为 `linux/amd64`。以下命令只检查本机镜像。

```bash
mapfile -t target_images < <(python3 - "$backup_dir/config.target.json" <<'PY'
import json
import sys
cfg = json.load(open(sys.argv[1]))
for name in ("backend", "frontend"):
    print(cfg["services"][name]["image"])
PY
)
test "${#target_images[@]}" -eq 2
for image_ref in "${target_images[@]}"; do
  docker image inspect "$image_ref" --format \
    '{{.Os}}/{{.Architecture}} {{.Id}} {{index .Config.Labels "org.opencontainers.image.revision"}} {{json .RepoDigests}}'
done
postgres_image_id=$(docker inspect --format '{{.Image}}' "$postgres_id")
docker image inspect "$postgres_image_id" --format '{{.Os}}/{{.Architecture}} {{.Id}}'
```

镜像站转存后的 manifest/index 摘要可能与 GHCR 不同。核实对应平台的 `config.digest`、本机 image ID 和 OCI revision，记录来源及验证方法。本次已对本机 Descriptor 中的 `config.digest` 与官方 GHCR 的 `linux/amd64` 配置摘要做一致性核对。单看相同标签无法验证镜像内容。

## 2. 在同一停写窗口备份数据库和附件

停止两个应用服务后，PG17 继续提供一致性 dump。用运行中数据库容器内的工具读取既有环境，密码不进入宿主命令参数。上传卷通过已有 PG 镜像中的 `tar` 只读挂载归档，容器创建时限制为本机镜像与无网络模式。

```bash
"${compose[@]}" stop frontend backend

"${compose[@]}" exec -T postgres sh -c \
  'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' \
  > "$backup_dir/database.dump"
test -s "$backup_dir/database.dump"
"${compose[@]}" exec -T postgres pg_restore --list \
  < "$backup_dir/database.dump" > "$backup_dir/database.list"

docker run --rm --pull never --network none --read-only \
  --entrypoint tar \
  --mount type=volume,source=multica_backend_uploads,target=/source,readonly \
  "$postgres_image_id" -C /source -czf - . > "$backup_dir/uploads.tar.gz"
test -s "$backup_dir/uploads.tar.gz"
tar -tzf "$backup_dir/uploads.tar.gz" > "$backup_dir/uploads.list"

(cd "$backup_dir"
  sha256sum database.dump uploads.tar.gz deployment.env \
    docker-compose.selfhost.yml docker-compose.easytier.yml > SHA256SUMS
  sha256sum --check SHA256SUMS)
```

归档目录可读取、校验和一致，表示文件已保存且格式可解析。数据库真正可恢复还要在独立实例和新卷完成 `pg_restore --exit-on-error`，核表结构和关键数量。附件恢复到独立目录或新卷，核对归档文件和内容。按同一停写时点配对数据库与附件。保留备份的私有权限及完成时间。 [PostgreSQL 17 备份格式](https://www.postgresql.org/docs/17/app-pgdump.html) · [恢复工具](https://www.postgresql.org/docs/17/app-pgrestore.html)

备份失败后保留停写状态和错误，核对原因并补齐备份。恢复旧应用继续服务须先核配置及数据库迁移状态，再决定恢复步骤。

## 3. 修改版本键并定向启动

`.env` 中版本值曾以单引号保存。下面只替换唯一的 `MULTICA_IMAGE_TAG` 行，统一写成 Compose 支持的单引号形式，通过同目录临时文件原子替换并保留 `root:root 0600`。如键缺失或重复，先核对配置。

```bash
python3 - "$deploy_dir/.env" "$target_tag" <<'PY'
import os
from pathlib import Path
import re
import stat
import sys
import tempfile

path, tag = Path(sys.argv[1]), sys.argv[2]
assert re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?", tag)
info = path.stat()
assert (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) == (0, 0, 0o600)
text, count = re.subn(r"(?m)^MULTICA_IMAGE_TAG[ \t]*=[^\r\n]*", f"MULTICA_IMAGE_TAG='{tag}'", path.read_bytes().decode())
assert count == 1, "需要唯一 MULTICA_IMAGE_TAG 行"
fd, temporary = tempfile.mkstemp(prefix=".env-upgrade-", dir=path.parent)
try:
    with os.fdopen(fd, "wb") as output:
        output.write(text.encode())
        output.flush()
        os.fsync(output.fileno())
        os.fchmod(output.fileno(), 0o600)
        os.fchown(output.fileno(), 0, 0)
    os.replace(temporary, path)
finally:
    if os.path.exists(temporary):
        os.unlink(temporary)
PY

"${compose[@]}" config --quiet
"${compose[@]}" config --format json > "$backup_dir/config.applied.json"
python3 - "$backup_dir/config.target.json" "$backup_dir/config.applied.json" <<'PY'
import json
import sys
target, applied = (json.load(open(p)) for p in sys.argv[1:])
assert target == applied, "实际配置与准备阶段不一致"
PY

"${compose[@]}" up -d --no-deps --pull never backend frontend
"${compose[@]}" ps
```

`--no-deps` 限定本次服务范围，`--pull never` 使用已经核验的本机镜像。新版 backend 启动后会运行数据库迁移。到此阶段，即使启动失败，也应先核迁移是否已执行。 [Compose 服务更新语义](https://docs.docker.com/reference/cli/docker/compose/up/)

## 4. 验收

先检查 PG healthy，再等应用 readiness。下例从运行中容器的 `NetworkSettings.Ports` 读取每一条实际绑定，检查环回与 RFC1918 私网端点。双绑定场景下，用 inspect 获取完整列表。遇到范围外的绑定先核对部署。

```bash
docker inspect --format '{{.State.Health.Status}}' "$postgres_id"
test "$(docker inspect --format '{{.State.Health.Status}}' "$postgres_id")" = healthy
backend_id=$("${compose[@]}" ps -q backend)
frontend_id=$("${compose[@]}" ps -q frontend)
python3 - "$backend_id" "$frontend_id" > "$backup_dir/endpoints.tsv" <<'PY'
import ipaddress
import json
import subprocess
import sys

private_ranges = [ipaddress.ip_network(cidr) for cidr in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")]
for name, container_id, port in zip(("backend", "frontend"), sys.argv[1:], (8080, 3000)):
    ports = json.loads(subprocess.check_output(["docker", "inspect", "--format", "{{json .NetworkSettings.Ports}}", container_id]))
    bindings = ports[f"{port}/tcp"]
    assert bindings, f"{name} 缺少端口绑定"
    for binding in bindings:
        address = ipaddress.ip_address(binding["HostIp"])
        assert address.is_loopback or any(address in net for net in private_ranges), "核对非环回/私网绑定"
        host = f"[{address}]" if address.version == 6 else str(address)
        kind = "loopback" if address.is_loopback else "private"
        print(kind, name, f"http://{host}:{binding['HostPort']}", sep="\t")
PY

while IFS=$'\t' read -r kind service endpoint; do
  if [[ "$service" == backend ]]; then
    ready_http=$(curl --retry 30 --retry-delay 2 --retry-connrefused --max-time 5 \
      -fsS -o "$backup_dir/readyz-$kind.json" -w '%{http_code}' "$endpoint/readyz")
    test "$ready_http" = 200
    python3 - "$backup_dir/readyz-$kind.json" <<'PY'
import json
import sys
data = json.load(open(sys.argv[1]))
assert data["status"] == "ok"
assert data["checks"]["db"] == data["checks"]["migrations"] == "ok"
print(json.dumps(data, ensure_ascii=False))
PY
    printf '%s Ready HTTP %s\n' "$kind" "$ready_http"
  else
    web_http=$(curl -fsS -o /dev/null -w '%{http_code}' "$endpoint/")
    test "$web_http" = 200
    printf '%s Web HTTP %s\n' "$kind" "$web_http"
  fi
done < "$backup_dir/endpoints.tsv"
"${compose[@]}" ps
docker inspect --format '{{.Name}} {{.Config.Image}} {{.Image}} restarts={{.RestartCount}} state={{.State.Status}}' \
  "$backend_id" "$frontend_id"
```

Web 返回页面后，从已连入 EasyTier 的真实客户端以既有端口访问，复查首页与 `/readyz`。如果配置仅私网绑定，应直接传对应 URL 核对，避免猜测接口或临时改绑定。失败日志先保存到私有目录，脱敏后附错误和时间。

核对迁移数量和已记录的关键业务数量。登录、WebSocket、Daemon 重连、实际 Run 与附件读写，逐项依据真实操作写回执。在确认业务恢复条件前保留维护窗口。记录验收时间、执行端、源 tag/commit、两镜像 ID/摘要、三个容器状态、重启次数、数据库及迁移状态、入口 HTTP、备份位置与恢复演练结果。

## 5. 验收后的旧应用镜像清理

本次获准删除 v0.9.0 和 v0.10.0 的应用镜像，包括已确认的 GHCR 与镜像站别名。先列出精确引用，核对每一项的版本、镜像 ID，以及所有容器的占用。将批准删除的完整 `repository:tag` 逐行存入私有备份目录下 `old-image-refs.approved`，只包含本次旧应用版本。

```bash
docker image ls --digests --no-trunc
# 检查并填写 old-image-refs.approved 后执行
while IFS= read -r image_ref; do
  test -n "$image_ref"
  case "$image_ref" in
    */multica-ai/multica-backend:v0.9.0|*/multica-ai/multica-backend:v0.10.0|\
    */multica-ai/multica-web:v0.9.0|*/multica-ai/multica-web:v0.10.0) ;;
    *) printf '清单中有未核对引用\n' >&2; exit 1 ;;
  esac
  test -z "$(docker ps -aq --filter "ancestor=$image_ref")"
  docker image rm "$image_ref"
done < "$backup_dir/old-image-refs.approved"
```

删除引用后，按记录的旧 image ID 逐一确认是否还存在其他别名，记录最终结果。PG17 镜像、运行中的目标应用镜像和原卷继续作为实例依赖。镜像清理使用上述精确清单，不使用 `prune` 或 `down -v`。旧版本重新获取仅使用上表对应的官方历史标签，并核对平台及来源。

## 6. 升级失败和迁移后的回退

保存失败时刻的配置、日志和数据库状态，暂停继续写入。只有证实新迁移尚未执行、旧应用与当前库兼容时，才可考虑用旧镜像恢复服务。

迁移已经执行或状态未知时，先把升级前 `database.dump` 恢复到独立 PG17 实例及新卷，并把同一备份时点的上传文件恢复到独立存储。用旧版本应用和备份配置连接该恢复环境，完成 readiness、关键记录与附件校验。保留升级后的原卷供取证和必要的数据补偿。数据库恢复至旧时点会影响此后新增或修改的数据，需明确恢复时点及数据处理方式。验证结果和具体切换步骤提交公子确认，获准后再回切生产入口。

回切方案应列明旧官方镜像标签和摘要、独立恢复卷、数据库连接、上传挂载、私网端口、待停止的服务、恢复时点和验收人。镜像改回旧 tag 无法撤销数据库前向迁移。任何改写生产库、替换原卷或执行 down migration 的步骤均需单独核准。本手册保留原卷，不提供覆盖唯一数据库的默认恢复命令。

## 升级回执

### 2026-11-26 升级回执

北京时间 15:50，腾讯云 Multica 由 `v0.12.1` 升至 `v0.13.0`。官方 tag 经临时 SSH 转发拉取，提交为 `35b54a3742bb51bdf5ffa688655367ec98044862`。停服前在途队列已归零。[官方发布](https://github.com/multica-ai/multica/releases/tag/v0.13.0)

| 项目 | 实测结果 |
|---|---|
| 前后端与配置 | backend/frontend 均为 `v0.13.0`，平台为 `linux/amd64`，镜像配置摘要均与官方 GHCR 一致。实际 Compose 等于官方 tag 中的文件，`.env` 的镜像标签已读回。 |
| 数据库与恢复 | 原 PG17 容器健康，数据库和附件备份校验通过，独立数据库恢复与迁移演练通过。生产迁移数由 758 增至 779。备份保留在宿主私有目录。 |
| 应用入口 | 环回和 EasyTier 入口的 API readiness 与 Web 均通过。从 mac-work 经私网访问，API 的 DB 和 migrations 均为 `ok`，Web 返回 HTTP 200。 |
| 下游检查 | mac-work CLI 与运行中 Daemon、Skill 版本参考和 Vultr MCP 的测试结果见 [v0.13.0 差异与验证](../skills/multica-backend/references/cli-v0.13.0.md#本轮验证)。 |

### 2026-11-19 升级回执

以下结果由本轮腾讯云 SSH 执行端回传，验收时间为 2026-11-19 09:21（Asia/Shanghai）。

| 项目 | 实测结果 |
|---|---|
| 仓库与源码 | `/opt/multica`，官方 `v0.11.0`，commit `cb190810a659c1a61c4a86d9f6ecfc9df4b086d8` |
| 应用容器 | backend/frontend 均 `v0.11.0`、running、重启次数 0 |
| 数据库 | 原 PG17 容器 healthy，原两个持久卷沿用 |
| 迁移与业务数量 | `schema_migrations` 684 → 708，issue 10、agent 11 均保持原数量 |
| 入口 | VPS 环回、VPS EasyTier 私网及 mac-work 经私网访问均 Web HTTP 200、`/readyz` HTTP 200 |
| Readiness | `{"status":"ok","checks":{"db":"ok","migrations":"ok"}}` |
| 镜像来源 | 两个 `linux/amd64` 平台的本机 config digest 与官方 GHCR 一致，OCI revision 均匹配本次 commit |
| 旧镜像清理 | 4 个唯一旧 image ID、8 个版本引用已明确删除，逐个 inspect 旧 ID 确认不存在 |
| 备份 | `/var/backups/multica/v0.10.0-before-v0.11.0-20261119T011953Z`，`database.dump` 为 3,614,898 字节，`uploads.tar.gz` 为 51,579 字节；五项 `SHA256SUMS` 通过，dump 目录与全文可解码 |
| 独立恢复演练 | 复用原 PG17 image ID，临时容器用 `--network none`、PGDATA tmpfs 和 `--rm`，`pg_restore --exit-on-error --no-owner --no-acl` 完整恢复成功，迁移/issue/agent 计数为 684/10/11，临时容器已停止并移除 |
| 已认证接口 | mac-work 已有登录会话通过 CLI 实际读回 workspace runtime 列表，共 8 条 |
| 额外业务验收 | 浏览器重新登录、WebSocket、Daemon 新任务和附件业务读写本轮待验 |

本次备份中的 `docker-compose.selfhost.yml` 来自运行中旧版 tag。配置文件 `deployment.env`、EasyTier override、dump 和附件只保留在 VPS 私有目录。当前升级回执补充原 Hindsight 手册 `multica-4-dot-selfhost-deploy-upgrade-runbook-v1-2026-11-16` 的部署实例信息，历史手册继续保留。
