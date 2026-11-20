"""Run one reconciliation cycle under current configuration and OAuth principal policy."""

import json
import os

from .gateway import Gateway


def main():
    policies = json.loads(os.environ["MULTICA_MCP_GITHUB_PRINCIPALS"])
    writers = {f"github:{subject}" for subject, policy in policies.items()
               if subject.isdecimal() and isinstance(policy, dict) and "write" in policy.get("scopes", [])}
    result = Gateway.from_env().recover(writers)
    print(json.dumps(result, sort_keys=True))
    return int(result["errors"] > 0)


if __name__ == "__main__":
    raise SystemExit(main())
