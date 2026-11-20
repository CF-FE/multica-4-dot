#!/usr/bin/env python3
"""Report public Multica releases and the repository's recorded compatibility baseline."""

import gzip
import html
import json
import re
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from http.client import HTTPException, IncompleteRead
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen


UPSTREAM = "https://github.com/multica-ai/multica"
RELEASES = f"{UPSTREAM}/releases"
API = "https://api.github.com/repos/multica-ai/multica/releases"
API_VERSION = "2026-03-10"
CATALOG = f"{API}?per_page=20"
METADATA = Path(__file__).resolve().parents[1] / "compatibility/multica-releases.json"
MAX_PAGES = 20
MAX_RESPONSE_BYTES = 16 * 1024 * 1024
STABLE_TAG = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")


class CheckError(Exception):
    pass


def version(tag):
    match = STABLE_TAG.fullmatch(tag)
    return tuple(map(int, match.groups())) if match else None


def tag_link(tag):
    return f"[<code>{html.escape(tag)}</code>]({RELEASES}/tag/{quote(tag, safe='')})"


@dataclass(frozen=True)
class Release:
    tag: str
    release_id: int
    published_at: str | None
    draft: bool
    prerelease: bool

    @property
    def formal(self):
        return not self.draft and not self.prerelease and self.published_at is not None

    @classmethod
    def from_api(cls, payload):
        if not isinstance(payload, dict):
            raise CheckError("GitHub Release 响应应为对象")
        tag = payload.get("tag_name")
        release_id = payload.get("id")
        draft = payload.get("draft")
        prerelease = payload.get("prerelease")
        published_at = payload.get("published_at")
        if (
            not isinstance(tag, str) or not tag or not tag.isprintable()
            or type(release_id) is not int or release_id < 1
            or type(draft) is not bool or type(prerelease) is not bool
            or (published_at is None and not draft)
        ):
            raise CheckError("GitHub Release 响应缺少有效的标签、ID、状态或发布时间")
        if published_at is not None:
            try:
                date = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                if date.tzinfo is None:
                    raise ValueError
                published_at = date.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            except (AttributeError, ValueError, OverflowError) as exc:
                raise CheckError("GitHub Release 的发布时间格式无效") from exc
        return cls(tag, release_id, published_at, draft, prerelease)


def fetch(url):
    request = Request(url, headers={
        "Accept": "application/vnd.github+json",
        "Accept-Encoding": "gzip",
        "User-Agent": "multica-4-dot-release-check",
        "X-GitHub-Api-Version": API_VERSION,
    })
    for attempt in range(2):
        try:
            return read_api_response(request)
        except (OSError, HTTPException, EOFError, ValueError, zlib.error) as exc:
            reason = exc.reason if isinstance(exc, URLError) else exc
            if attempt == 0 and isinstance(reason, (IncompleteRead, TimeoutError, ConnectionError, EOFError)):
                continue
            raise CheckError(f"读取 GitHub API 失败（{type(reason).__name__}）") from exc


def read_api_response(request):
    try:
        with urlopen(request, timeout=25) as response:
            if response.url != request.full_url:
                raise CheckError("GitHub API 地址已重定向，请核对官方仓库地址")
            if response.headers.get("Content-Encoding") == "gzip":
                with gzip.GzipFile(fileobj=response) as compressed:
                    body = compressed.read(MAX_RESPONSE_BYTES + 1)
            else:
                body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                raise CheckError("GitHub API 单页响应超过大小限制")
            return json.loads(body), ",".join(response.headers.get_all("Link", []))
    except HTTPError as exc:
        headers = exc.headers
        status = exc.code
        exc.close()
        retry = headers.get("Retry-After", "")
        reset = headers.get("X-RateLimit-Reset", "")
        if status == 429 or (status == 403 and (retry or headers.get("X-RateLimit-Remaining") == "0")):
            advice = "请等待至少 60 秒再手动重跑"
            if retry.isdecimal():
                advice = f"请等待至少 {retry} 秒再重跑"
            elif headers.get("X-RateLimit-Remaining") == "0" and reset.isdecimal():
                advice = f"请在 GitHub 配额重置后重跑（Unix 秒 {reset}）"
            raise CheckError(f"GitHub API 限流（HTTP {status}）。{advice}。") from exc
        if status == 410:
            raise CheckError(f"GitHub API 返回 HTTP 410，请核对固定 API 版本 {API_VERSION}") from exc
        if status == 403:
            raise CheckError("GitHub API 返回 HTTP 403，请核对访问策略和次级配额") from exc
        raise CheckError(f"GitHub API 返回 HTTP {status}") from exc


def list_releases():
    releases = {}
    visited = set()
    url = CATALOG
    for page in range(1, MAX_PAGES + 1):
        if url in visited:
            raise CheckError("GitHub Releases 分页出现循环")
        visited.add(url)
        try:
            payload, links = fetch(url)
        except CheckError as exc:
            raise CheckError(f"发布列表第 {page} 页。{exc}") from exc
        if not isinstance(payload, list):
            raise CheckError("GitHub Releases 列表响应应为数组")
        for entry in payload:
            release = Release.from_api(entry)
            if release.tag in releases:
                raise CheckError("GitHub Releases 分页出现重复标签，请重跑以获取一致结果")
            releases[release.tag] = release

        next_links = re.findall(r'<([^<>]+)>\s*;\s*rel="next"', links)
        if not next_links:
            return releases
        url = next_links[0]
        target = urlsplit(url)
        if (
            len(next_links) != 1 or target.scheme != "https" or target.netloc != "api.github.com"
            or target.path not in (urlsplit(API).path, "/repositories/1133707766/releases")
            or not target.query or target.fragment
        ):
            raise CheckError("GitHub Releases 返回意外的分页地址")
    raise CheckError(f"GitHub Releases 超过 {MAX_PAGES} 页，候选列表未完整读取")


def report(metadata):
    baseline = metadata["baseline"]
    baseline_tag = baseline["tag"]
    baseline_version = version(baseline_tag)
    if baseline_version is None:
        raise CheckError("部署比较基线须为 vMAJOR.MINOR.PATCH")
    observed = metadata["production_last_observed"]
    lines = [
        "## Multica 上游发行版检查",
        "",
        f"- 检查时间（UTC）`{datetime.now(timezone.utc).isoformat(timespec='seconds')}`",
        f"- 已核实的 Multica 部署比较基线 {tag_link(baseline_tag)}，"
        f"源码提交 `{baseline['commit']}`，依据 `{baseline['evidence']}`。",
        "- 候选版 MCP 实例读／写兼容性 **UNKNOWN**，由隔离实例验证取证。",
        "- 当前生产版本 **UNKNOWN**。",
    ]
    if observed is not None:
        lines.append(
            f"- 生产最近核实的应用镜像标签 {tag_link(observed['tag'])}（`{observed['observed_at']}`），"
            f"依据 `{observed['evidence']}`。"
        )

    latest_line = "- GitHub 标记的最新正式版 **UNKNOWN**。"
    try:
        payload, _ = fetch(f"{API}/latest")
        latest = Release.from_api(payload)
        if not latest.formal:
            raise CheckError("GitHub latest 端点未返回公开的正式发布")
        latest_line = (
            f"- GitHub 标记的最新正式版 {tag_link(latest.tag)}"
            f"（`{latest.published_at}`，Release ID `{latest.release_id}`）。"
        )
        releases = list_releases()
        if releases.get(latest.tag) != latest:
            latest_line = "- GitHub 标记的最新正式版 **UNKNOWN**。"
            raise CheckError("GitHub latest 与发布列表不一致，请重跑核实")
    except CheckError as exc:
        lines.extend([latest_line, "- 升级候选 **UNKNOWN**。", f"- 读取失败。{html.escape(str(exc))}"])
        return "\n".join(lines), 1
    lines.append(latest_line)

    baseline_release = releases.get(baseline_tag)
    if not baseline_release or not baseline_release.formal or baseline_release.release_id != baseline["release_id"]:
        lines.append("- 基线的公开 Release 缺失、状态已变或 ID 不符。升级候选 **UNKNOWN**，请核实上游记录。")
        return "\n".join(lines), 1

    held = set()
    incomplete = False
    for tag, tracked in metadata["tracked"].items():
        release = releases.get(tag)
        if tracked.get("withdrawn_evidence"):
            held.add(tag)
            lines.append(f"- {tag_link(tag)} 已记录撤回，依据 `{tracked['withdrawn_evidence']}`。")
        elif not release or not release.formal or release.release_id != tracked["release_id"]:
            held.add(tag)
            incomplete = True
            lines.append(f"- {tag_link(tag)} 的公开 Release 缺失、状态已变或 ID 不符。撤回原因 **UNKNOWN**，暂停评估。")

    candidates = []
    for release in releases.values():
        if not release.formal or release.tag in held:
            continue
        release_version = version(release.tag)
        if release_version is None:
            lines.append(f"- 正式发布 {tag_link(release.tag)} 无法按 vMAJOR.MINOR.PATCH 比较，候选资格 **UNKNOWN**。")
            incomplete = True
        elif release_version > baseline_version:
            candidates.append((release_version, release))

    if candidates:
        lines.extend(["", "### 升级候选（待验证）", ""])
        base_ref = quote(baseline["commit"], safe="")
        for _, release in sorted(candidates):
            compare = f"{UPSTREAM}/compare/{base_ref}...{quote(release.tag, safe='')}"
            lines.append(
                f"- {tag_link(release.tag)}（`{release.published_at}`，Release ID `{release.release_id}`）"
                f" · [基线至此版本的变更]({compare})"
            )
    elif incomplete:
        lines.append("- 升级候选 **UNKNOWN**，目前无可列出的候选。")
    else:
        lines.append("- 当前目录中没有高于基线且可评估的正式发布。")
    return "\n".join(lines), int(incomplete)


def main():
    try:
        metadata = json.loads(METADATA.read_text(encoding="utf-8"))
        summary, status = report(metadata)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, CheckError) as exc:
        print(f"Multica 版本检查 **UNKNOWN**。请核对版本记录（{html.escape(str(exc))}）。")
        return 1
    print(summary)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
