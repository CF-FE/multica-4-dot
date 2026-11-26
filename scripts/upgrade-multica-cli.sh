#!/bin/bash
set -euo pipefail

usage() {
  cat <<'USAGE'
用法：upgrade-multica-cli.sh [--check]

升级 macOS 上由 Homebrew 安装的 Multica CLI，保留旧版本。
--check  查看当前 CLI、官方 tap 是否已同步和本地配方版本。
MULTICA_UPGRADE_PROXY 可指定本次使用的代理 URL，适用于按域名分流的 PAC。
USAGE
}

fail() {
  printf '升级失败：%s\n' "$*" >&2
  exit 1
}

case "${1:-}" in
  -h|--help) usage; exit 0 ;;
  ''|--check) [[ $# -le 1 ]] || fail '参数过多。' ;;
  *) usage >&2; exit 2 ;;
esac

[[ "$(/usr/bin/uname -s)" == Darwin ]] || fail '此脚本适用于 macOS。'
cli=$(type -P multica) || fail 'PATH 中找不到 multica。'
case "$cli" in
  /usr/local/bin/multica) brew=(/usr/bin/arch -x86_64 /usr/local/bin/brew) ;;
  /opt/homebrew/bin/multica) brew=(/usr/bin/arch -arm64 /opt/homebrew/bin/brew) ;;
  *) fail "未识别到 Homebrew 管理的 CLI：$cli" ;;
esac
[[ -x "${brew[2]}" ]] || fail "找不到 Homebrew：${brew[2]}"

export HOMEBREW_NO_AUTO_UPDATE=1 HOMEBREW_NO_INSTALL_CLEANUP=1
export HOMEBREW_NO_INSTALLED_DEPENDENTS_CHECK=1 GIT_OPTIONAL_LOCKS=0

formula=multica-ai/tap/multica
tap_dir=$("${brew[@]}" --repository multica-ai/tap)
installed_prefix=$("${brew[@]}" --prefix "$formula")
[[ "$cli" -ef "$installed_prefix/bin/multica" ]] || fail "当前 CLI 与 Homebrew 链接不一致：$cli"

tap_git=(/usr/bin/git -C "$tap_dir")
origin=$("${tap_git[@]}" remote get-url origin)
case "$origin" in
  https://github.com/multica-ai/homebrew-tap|https://github.com/multica-ai/homebrew-tap.git) ;;
  *) fail 'Multica tap 的 origin 与官方仓库不一致。' ;;
esac
[[ "$("${tap_git[@]}" symbolic-ref --quiet --short HEAD)" == main ]] || fail 'Multica tap 未检出 main。'
[[ -z "$("${tap_git[@]}" status --porcelain)" ]] || fail 'Multica tap 有本地改动，请先处理。'

proxy=${MULTICA_UPGRADE_PROXY:-}
use_proxy_override=${MULTICA_UPGRADE_PROXY+x}
if [[ -z "$use_proxy_override" ]]; then
  proxy_settings=$(/usr/sbin/scutil --proxy)
  pac_enabled=$(printf '%s\n' "$proxy_settings" | /usr/bin/awk '$1 == "ProxyAutoConfigEnable" {print $3; exit}')
  if [[ "$pac_enabled" == 1 ]]; then
    pac_url=$(printf '%s\n' "$proxy_settings" | /usr/bin/awk '$1 == "ProxyAutoConfigURLString" {print $3; exit}')
    [[ -n "$pac_url" ]] || fail '系统已启用 PAC，但没有 PAC 地址。'
    # This Mac's PAC returns one constant route list. Never execute downloaded PAC code.
    primary_route=$(
      /usr/bin/curl --noproxy '*' --proto '=http,https' -fsSL --max-time 10 "$pac_url" |
        LC_ALL=C /usr/bin/perl -0777 -ne '
          /\A\s*function\s+FindProxyForURL\s*\(\s*\w+\s*,\s*\w+\s*\)\s*\{\s*return\s+(["\x27])([^"\x27\r\n]+)\1\s*;?\s*\}\s*\z/ or exit 1;
          ($route) = split /;/, $2;
          $route =~ s/^\s+|\s+$//g;
          print $route;
        '
    ) || fail '无法读取静态 PAC 路由，可用 MULTICA_UPGRADE_PROXY 指定代理。'
    case "$primary_route" in
      'PROXY '*) proxy="http://${primary_route#PROXY }" ;;
      'HTTPS '*) proxy="https://${primary_route#HTTPS }" ;;
      'SOCKS5 '*) proxy="socks5h://${primary_route#SOCKS5 }" ;;
      DIRECT) proxy= ;;
      *) fail 'PAC 的首选路由无法用于 Git 和 Homebrew。' ;;
    esac
    use_proxy_override=1
    printf '已读取系统 PAC 的首选路由。\n'
  fi
fi

if [[ -n "$use_proxy_override" ]]; then
  export http_proxy="$proxy" https_proxy="$proxy" HTTP_PROXY="$proxy" HTTPS_PROXY="$proxy"
  export no_proxy='' NO_PROXY='' all_proxy='' ALL_PROXY=''
  tap_git+=(-c "http.$origin.proxy=$proxy")
fi
tap_git+=(-c http.lowSpeedLimit=1024 -c http.lowSpeedTime=30)

printf '当前 CLI\n'
"$cli" --version
head=$("${tap_git[@]}" rev-parse HEAD)
if [[ "${1:-}" == --check ]]; then
  remote_head=$("${tap_git[@]}" ls-remote --exit-code origin refs/heads/main)
  if [[ "$head" == "${remote_head%%[[:space:]]*}" ]]; then
    printf '\n官方 tap 已同步。\n'
  else
    printf '\n本地 tap 与官方 main 不同，升级时会检查能否快进。\n'
  fi
  "${brew[@]}" info --formula "$formula"
  exit 0
fi

"${tap_git[@]}" fetch --no-tags --no-recurse-submodules origin refs/heads/main:refs/remotes/origin/main
upstream=$("${tap_git[@]}" rev-parse refs/remotes/origin/main)
if [[ "$head" != "$upstream" ]]; then
  "${tap_git[@]}" merge-base --is-ancestor "$head" "$upstream" || fail 'Multica tap 无法快进到官方 main。'
  "${tap_git[@]}" merge --ff-only "$upstream"
fi

"${brew[@]}" upgrade --formula "$formula"
printf '\n升级后 CLI\n'
"$cli" --version
