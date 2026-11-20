import gzip
import json
import unittest
from email.message import Message
from http.client import IncompleteRead
from io import BytesIO
from unittest.mock import call, patch
from urllib.error import HTTPError, URLError

from scripts import check_multica_release as checker


BASELINE = "v0.11.0"
WATCHED = "v0.11.1"
LATEST_URL = f"{checker.API}/latest"
SECOND_PAGE = "https://api.github.com/repositories/1133707766/releases?per_page=20&page=2"


def release(tag, release_id, *, draft=False, prerelease=False):
    return {
        "tag_name": tag,
        "id": release_id,
        "published_at": None if draft else "2026-11-19T10:12:27Z",
        "draft": draft,
        "prerelease": prerelease,
        "body": "Untrusted release notes must stay out of the report.",
    }


class ReleaseReportTests(unittest.TestCase):
    def setUp(self):
        self.baseline = release(BASELINE, 1)
        self.watched = release(WATCHED, 2)
        self.metadata = {
            "baseline": {"tag": BASELINE, "release_id": 1, "commit": "a" * 40, "evidence": "baseline-receipt"},
            "production_last_observed": {
                "tag": "v0.10.0", "observed_at": "2026-11-19T09:21:00+08:00", "evidence": "production-receipt",
            },
            "tracked": {WATCHED: {"release_id": 2}},
        }

    def test_multiple_pages_and_version_jump_keep_github_latest_distinct(self):
        next_link = f'<{SECOND_PAGE}>; rel="next"'
        with patch.object(checker, "fetch", side_effect=[
            (self.watched, ""),
            ([self.watched, release("v0.11.10", 10), release("v0.12.0", 12, prerelease=True)], next_link),
            ([self.baseline, release("v0.11.2", 3), release("v1.0.0", 20, draft=True)], ""),
        ]) as fetch:
            report, status = checker.report(self.metadata)

        self.assertEqual(fetch.call_args_list, [call(LATEST_URL), call(checker.CATALOG), call(SECOND_PAGE)])
        self.assertEqual(status, 0, report)
        self.assertIn("GitHub 标记的最新正式版 [<code>v0.11.1", report)
        self.assertIn("已核实的 Multica 部署比较基线 [<code>v0.11.0", report)
        self.assertIn("候选版 MCP 实例读／写兼容性 **UNKNOWN**", report)
        self.assertNotIn("已验证基线", report)
        self.assertIn("当前生产版本 **UNKNOWN**", report)
        self.assertIn("生产最近核实的应用镜像标签 [<code>v0.10.0", report)
        self.assertIn("2026-11-19T09:21:00+08:00`），依据 `production-receipt`", report)
        candidates = report.split("### 升级候选（待验证）")[1]
        self.assertLess(candidates.index(WATCHED), candidates.index("v0.11.2"))
        self.assertLess(candidates.index("v0.11.2"), candidates.index("v0.11.10"))
        for tag in (WATCHED, "v0.11.2", "v0.11.10"):
            compare = f"https://github.com/multica-ai/multica/compare/{'a' * 40}...{tag}"
            self.assertTrue(any(f"/tag/{tag})" in line and compare in line for line in candidates.splitlines()))
        for hidden in ("v0.12.0", "v1.0.0", "Untrusted release notes"):
            self.assertNotIn(hidden, report)

    def test_missing_replaced_or_prerelease_candidate_needs_review(self):
        for entries in ([], [release(WATCHED, 3)], [release(WATCHED, 2, prerelease=True)]):
            with self.subTest(entries=entries), patch.object(checker, "fetch", side_effect=[
                (self.baseline, ""), ([self.baseline, *entries], ""),
            ]):
                report, status = checker.report(self.metadata)
                self.assertEqual(status, 1, report)
                self.assertIn("撤回原因 **UNKNOWN**", report)
                self.assertNotIn("### 升级候选", report)

    def test_confirmed_withdrawal_excludes_even_a_still_public_release(self):
        self.metadata["tracked"][WATCHED]["withdrawn_evidence"] = "upstream-withdrawal-notice"
        with patch.object(checker, "fetch", side_effect=[
            (self.watched, ""), ([self.watched, self.baseline], ""),
        ]):
            report, status = checker.report(self.metadata)
        self.assertEqual(status, 0, report)
        self.assertIn("GitHub 标记的最新正式版 [<code>v0.11.1", report)
        self.assertIn("已记录撤回，依据 `upstream-withdrawal-notice`", report)
        self.assertIn("没有高于基线且可评估的正式发布", report)

    def test_missing_baseline_does_not_replace_historical_reference(self):
        with patch.object(checker, "fetch", side_effect=[(self.watched, ""), ([self.watched], "")]):
            report, status = checker.report(self.metadata)
        self.assertEqual(status, 1, report)
        self.assertIn("已核实的 Multica 部署比较基线 [<code>v0.11.0", report)
        self.assertIn("升级候选 **UNKNOWN**", report)

    def test_later_page_failure_keeps_observed_latest_and_marks_candidates_unknown(self):
        with patch.object(checker, "fetch", side_effect=[
            (self.watched, ""), ([self.watched], f'<{SECOND_PAGE}>; rel="next"'),
            checker.CheckError("fixture page unavailable"),
        ]):
            report, status = checker.report(self.metadata)
        self.assertEqual(status, 1, report)
        self.assertIn("GitHub 标记的最新正式版 [<code>v0.11.1", report)
        self.assertIn("升级候选 **UNKNOWN**", report)
        self.assertIn("发布列表第 2 页。fixture page unavailable", report)

    def test_rejects_inconsistent_latest(self):
        with patch.object(checker, "fetch", side_effect=[(self.watched, ""), ([self.baseline], "")]):
            report, status = checker.report(self.metadata)
        self.assertEqual(status, 1, report)
        self.assertIn("GitHub 标记的最新正式版 **UNKNOWN**", report)

    def test_nonstandard_formal_tag_is_visible_but_not_compared(self):
        unusual = release("next<preview>", 3)
        with patch.object(checker, "fetch", side_effect=[
            (unusual, ""), ([self.baseline, self.watched, unusual], ""),
        ]):
            report, status = checker.report(self.metadata)
        self.assertEqual(status, 1, report)
        self.assertIn("next&lt;preview&gt;", report)
        self.assertIn("候选资格 **UNKNOWN**", report)
        self.assertNotIn("next<preview>", report)

    def test_rejects_cross_repo_pagination(self):
        link = '<https://api.github.com/repos/another/project/releases?page=2>; rel="next"'
        with patch.object(checker, "fetch", return_value=([self.watched], link)) as fetch:
            with self.assertRaisesRegex(checker.CheckError, "意外的分页地址"):
                checker.list_releases()
        fetch.assert_called_once_with(checker.CATALOG)

    def test_page_bound_and_pagination_loop(self):
        link = f'<{SECOND_PAGE}>; rel="next"'
        with patch.object(checker, "fetch", return_value=([], link)) as fetch:
            with self.assertRaisesRegex(checker.CheckError, "分页出现循环"):
                checker.list_releases()
        self.assertEqual(fetch.call_count, 2)
        with patch.object(checker, "MAX_PAGES", 1), patch.object(checker, "fetch", return_value=([], link)):
            with self.assertRaisesRegex(checker.CheckError, "超过 1 页"):
                checker.list_releases()


class GitHubReadTests(unittest.TestCase):
    def test_reads_compressed_public_response(self):
        payload = release(WATCHED, 2)
        response = BytesIO(gzip.compress(json.dumps(payload).encode()))
        response.url = LATEST_URL
        response.headers = Message()
        response.headers["Content-Encoding"] = "gzip"
        with patch.object(checker, "urlopen", return_value=response):
            self.assertEqual(checker.fetch(LATEST_URL), (payload, ""))

    def test_retries_an_incomplete_response_once(self):
        payload = release(WATCHED, 2)
        response = BytesIO(json.dumps(payload).encode())
        response.url = LATEST_URL
        response.headers = Message()
        with patch.object(checker, "urlopen", side_effect=[IncompleteRead(b''), response]) as open_url:
            self.assertEqual(checker.fetch(LATEST_URL), (payload, ""))
        self.assertEqual(open_url.call_count, 2)

    def test_http_errors_explain_failure_without_retry(self):
        cases = [
            (403, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1795158634"}, "配额重置.*1795158634"),
            (429, {"Retry-After": "30"}, "限流.*30 秒"),
            (429, {}, "限流.*60 秒"),
            (403, {}, "返回 HTTP 403"),
            (404, {}, "返回 HTTP 404"),
            (410, {}, f"固定 API 版本 {checker.API_VERSION}"),
        ]
        for status, fields, diagnostic in cases:
            headers = Message()
            for name, value in fields.items():
                headers[name] = value
            error = HTTPError(LATEST_URL, status, "status", headers, None)
            with self.subTest(status=status, fields=fields), patch.object(checker, "urlopen", side_effect=error) as open_url:
                with self.assertRaisesRegex(checker.CheckError, diagnostic):
                    checker.fetch(LATEST_URL)
                open_url.assert_called_once()
                request = open_url.call_args.args[0]
                self.assertEqual(request.get_method(), "GET")
                self.assertEqual(request.get_header("X-github-api-version"), checker.API_VERSION)
                self.assertIsNone(request.get_header("Authorization"))

    def test_timeout_is_reported_as_a_read_failure(self):
        with patch.object(checker, "urlopen", side_effect=URLError(TimeoutError())) as open_url:
            with self.assertRaisesRegex(checker.CheckError, "TimeoutError"):
                checker.fetch(LATEST_URL)
        self.assertEqual(open_url.call_count, 2)


if __name__ == "__main__":
    unittest.main()
