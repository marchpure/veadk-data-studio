from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    evidence_dir = Path(os.environ.get("EVIDENCE_DIR", "/tmp/veadk-data-studio-evaluation-sharing-e2e"))
    evidence_dir.mkdir(parents=True, exist_ok=True)
    log_path = evidence_dir / "cross-module-e2e-pytest.log"
    command = [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_evaluation_sharing_cross_module_e2e.py",
        "-q",
    ]
    env = {
        **os.environ,
        "PYTHONPATH": "..:tests",
    }
    started_at = datetime.now(UTC).isoformat()
    process = subprocess.run(
        command,
        cwd=repo_root / "server",
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    log_path.write_text(process.stdout, encoding="utf-8")
    summary = {
        "ok": process.returncode == 0,
        "returncode": process.returncode,
        "started_at": started_at,
        "finished_at": datetime.now(UTC).isoformat(),
        "command": " ".join(command),
        "log": str(log_path),
        "coverage": [
            "local CSV source upload",
            "source snapshot and projection review",
            "semantic draft/publish and MCP query",
            "dashboard create/publish/query and MCP parity",
            "evaluation import/publish/preflight/run and MCP parity",
            "sharing folder grant/read/revoke and MCP parity",
            "tenant/idempotency/lineage/redaction assertions",
        ],
        "external_owner_blockers_expected": [
            {
                "owner": "Modeling",
                "summary": "Projected CSV semantic draft can select a non-numeric generated metric; the journey records this as blocker evidence without modifying Modeling production code.",
            }
        ],
    }
    summary_path = evidence_dir / "cross-module-e2e-summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    if process.returncode != 0:
        print(process.stdout)
    return process.returncode


if __name__ == "__main__":
    raise SystemExit(main())
