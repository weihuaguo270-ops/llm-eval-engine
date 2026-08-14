"""Audit portfolio evidence before selecting a target role."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from eval_engine.readiness import audit_role_readiness, role_catalog


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--role", choices=tuple(role_catalog()), action="append")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    source = json.loads(args.manifest.read_text(encoding="utf-8"))
    reports = [audit_role_readiness(role, source.get("evidence") or {})
               for role in (args.role or list(role_catalog()))]
    payload = {"portfolio": source.get("portfolio", ""),
               "evidence_version": source.get("evidence_version", ""), "reports": reports}
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if all(report["resume_ready"] for report in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
