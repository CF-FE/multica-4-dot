"""Probe the Multica read contract with a configured test environment and fixture IDs."""

import argparse
import json
import os
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcp"))

from multica_backend.multica_api import CONTRACT_BASELINE, CONTRACT_SOURCE_COMMIT, MulticaAPI, MulticaAPIError


class Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's diagnostics can repeat untrusted argument values verbatim.
        raise MulticaAPIError("configuration", "invalid_arguments")


def main(argv=None):
    parser = Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--live", action="store_true", help="enable GETs to the specified test API")
    parser.add_argument("--origin", help="operator-verified test API origin")
    parser.add_argument("--allow-private-http", action="store_true",
                        help="allow a fixed RFC 1918 IPv4 origin on a verified encrypted overlay")
    parser.add_argument("--expected-user-id", help="expected UUID from /api/me")
    parser.add_argument("--workspace-id", help="test workspace UUID")
    parser.add_argument("--project-id", help="test project UUID")
    parser.add_argument("--issue-id", help="fixture Issue UUID in that project")
    parser.add_argument("--run-id", help="exact fixture Run UUID on that Issue")
    parser.add_argument("--candidate-version", help="operator-supplied release label (vX.Y.Z), not server detection")
    parser.epilog = ("Provide the test bearer in MULTICA_CONTRACT_TOKEN. Exit 0 when checks pass, "
                     "1 on a failed read check, or 2 when the probe cannot start.")

    candidate = None
    try:
        args = parser.parse_args(argv)
        if not args.live:
            raise MulticaAPIError("configuration", "live_not_requested")
        if args.candidate_version is not None:
            if re.fullmatch(r"v[0-9]{1,8}\.[0-9]{1,8}\.[0-9]{1,8}", args.candidate_version) is None:
                raise MulticaAPIError("configuration", "invalid_input", field="candidate_version")
            candidate = args.candidate_version
        for field in ("origin", "expected_user_id", "workspace_id", "project_id", "issue_id", "run_id"):
            if not getattr(args, field):
                raise MulticaAPIError("configuration", "missing_input", field=field)
        token = os.environ.get("MULTICA_CONTRACT_TOKEN")
        if not token:
            raise MulticaAPIError("configuration", "missing_credential")
        api = MulticaAPI(origin=args.origin, token=token, expected_user_id=args.expected_user_id,
                         workspace_id=args.workspace_id, project_id=args.project_id,
                         allow_private_http=args.allow_private_http)
        report = api.check_contract(args.issue_id, args.run_id)
    except MulticaAPIError as exc:
        report = {"schema_version": 1, "contract_baseline": CONTRACT_BASELINE,
                  "contract_source_commit": CONTRACT_SOURCE_COMMIT, "status": "not_run",
                  "checks": [{"check": exc.check, "status": "fail", **exc.diagnostic()}]}

    report["candidate_version"] = candidate
    print(json.dumps(report, sort_keys=True))
    return {"pass": 0, "fail": 1, "not_run": 2}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
