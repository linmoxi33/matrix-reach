"""CLI + rule-level mutation self-test for matrix_reach."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import audit_workflow_text

RULES = {
    "MR001": "duplicate expanded combination",
    "MR002": "exclude matches no combination",
    "MR003": "include value is not in the axis (creates an extra combo)",
    "MR004": "include matches no base combo (creates an extra combo)",
    "MR005": "exclude key is not an axis",
    "MR006": "matrix.<key> referenced but never defined",
    "MR007": "max-parallel exceeds the number of combinations",
    "MR008": "fail-fast is not a boolean",
    "MR010": "include/exclude is not a list of mappings",
    "MR011": "exclude value is not in the axis (can never match)",
}

_FIXTURES = {
    "MR001": """
jobs:
  b:
    strategy:
      matrix:
        os: [linux, linux]
    steps: [{run: "echo ${{ matrix.os }}"}]
""",
    "MR002": """
jobs:
  b:
    strategy:
      matrix:
        os: [linux]
        exclude: [{os: windows}]
    steps: [{run: "echo ${{ matrix.os }}"}]
""",
    "MR003": """
jobs:
  b:
    strategy:
      matrix:
        os: [linux, windows]
        include: [{os: macos, extra: 1}]
    steps: [{run: "echo ${{ matrix.os }}"}]
""",
    "MR004": """
jobs:
  b:
    strategy:
      matrix:
        os: [linux]
        arch: [x86]
        include: [{os: linux, arch: arm}]
    steps: [{run: "echo ${{ matrix.os }}"}]
""",
    "MR005": """
jobs:
  b:
    strategy:
      matrix:
        os: [linux]
        exclude: [{platform: windows}]
    steps: [{run: "echo ${{ matrix.os }}"}]
""",
    "MR006": """
jobs:
  b:
    strategy:
      matrix:
        os: [linux]
    steps: [{run: "echo ${{ matrix.python }}"}]
""",
    "MR007": """
jobs:
  b:
    strategy:
      max-parallel: 9
      matrix:
        os: [linux, windows]
    steps: [{run: "echo ${{ matrix.os }}"}]
""",
    "MR008": """
jobs:
  b:
    strategy:
      fail-fast: "yes"
      matrix:
        os: [linux]
    steps: [{run: "echo ${{ matrix.os }}"}]
""",
    "MR011": """
jobs:
  b:
    strategy:
      matrix:
        os: [linux]
        exclude: [{os: ubuntu}]
    steps: [{run: "echo ${{ matrix.os }}"}]
""",
    "MR010": """
jobs:
  b:
    strategy:
      matrix:
        os: [linux]
        include: not-a-list
    steps: [{run: "echo ${{ matrix.os }}"}]
""",
}


def self_test() -> tuple[bool, list[dict]]:
    out = []
    ok_all = True
    for rule, text in _FIXTURES.items():
        results = audit_workflow_text(text)
        found = sorted({p["rule"] for r in results for p in r.problems})
        ok = rule in found
        ok_all &= ok
        out.append({"rule": rule, "expected": RULES[rule], "found": found, "ok": ok})
    return ok_all, out


def scan(paths: list[str]) -> dict:
    files, matrices, skipped = [], 0, 0
    errors, notes = [], []
    combos = 0
    for raw in paths:
        p = Path(raw)
        candidates = sorted(p.rglob("*.yml")) + sorted(p.rglob("*.yaml")) if p.is_dir() else [p]
        for f in candidates:
            try:
                text = f.read_text(encoding="utf-8")
                results = audit_workflow_text(text)
            except Exception as exc:  # noqa: BLE001 - report parse failures as findings
                errors.append({"file": str(f), "rule": "MR000", "detail": f"parse error: {exc}"})
                continue
            files.append(str(f))
            for r in results:
                matrices += 1
                if r.skipped:
                    skipped += 1
                    continue
                combos += len(r.final)
                for prob in r.problems:
                    row = {"file": str(f), **prob}
                    (notes if prob.get("severity") == "note" else errors).append(row)
    return {"files": len(files), "matrices": matrices, "skipped": skipped,
            "combinations": combos, "errors": errors, "notes": notes,
            "problems": errors + notes}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="matrix-reach")
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        ok, rows = self_test()
        print(json.dumps({"ok": ok, "rules": rows}, indent=2, ensure_ascii=False))
        return 0 if ok else 2

    if not args.paths:
        print("matrix-reach: give a file/directory or --self-test", file=sys.stderr)
        return 2
    report = scan(args.paths)
    if not args.json:
        print(f"files={report['files']} matrices={report['matrices']} "
              f"skipped={report['skipped']} combinations={report['combinations']} "
              f"errors={len(report['errors'])} notes={len(report['notes'])}")
        for row in report["errors"] + report["notes"]:
            print(f"  [{row['rule']}] {row['file']}: {row['detail']}")
    else:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
