"""Exact GitHub Actions matrix expansion + reachability audit.

The expander implements the documented include/exclude order:

1. cartesian product of the axis arrays;
2. ``exclude`` removes combinations that contain every key/value pair;
3. each ``include`` entry augments matching combinations; if it matches none
   (including when it would overwrite an axis value), it becomes a new combination.

The audit reports only facts about that expansion, never a guess about intent.
"""

from __future__ import annotations

import itertools
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MatrixResult:
    job: str
    axes: dict[str, list]
    base: list[dict]
    after_exclude: list[dict]
    final: list[dict]
    excluded: int
    added: int
    problems: list[dict] = field(default_factory=list)
    skipped: str | None = None

    def as_dict(self) -> dict:
        return {
            "job": self.job,
            "axes": self.axes,
            "base_count": len(self.base),
            "after_exclude_count": len(self.after_exclude),
            "final_count": len(self.final),
            "excluded": self.excluded,
            "added": self.added,
            "problems": self.problems,
            "skipped": self.skipped,
        }


def _matches(combo: dict, pattern: dict) -> bool:
    return all(k in combo and combo[k] == v for k, v in pattern.items())


def expand_matrix(job: str, matrix: Any, strategy: dict | None = None) -> MatrixResult:
    if not isinstance(matrix, dict):
        return MatrixResult(job, {}, [], [], [], 0, 0, skipped="matrix is not a mapping")
    def has_expr(v):
        if isinstance(v, str):
            return "${{" in v
        if isinstance(v, list):
            return any(has_expr(x) for x in v)
        if isinstance(v, dict):
            return any(has_expr(x) for x in v.values())
        return False
    if has_expr(matrix):
        return MatrixResult(job, {}, [], [], [], 0, 0,
                            skipped="matrix uses an expression; static expansion is unsound")
    axes = {k: v for k, v in matrix.items() if k not in ("include", "exclude")}
    for k, v in axes.items():
        if not isinstance(v, list) or not v:
            return MatrixResult(job, axes, [], [], [], 0, 0,
                                skipped=f"axis {k!r} is not a non-empty list")
    keys = list(axes)
    base = [dict(zip(keys, vals)) for vals in itertools.product(*(axes[k] for k in keys))] if keys else []
    problems: list[dict] = []

    excludes = matrix.get("exclude") or []
    if not isinstance(excludes, list):
        excludes = []
        problems.append({"rule": "MR010", "detail": "exclude is not a list"})
    after = list(base)
    removed = 0
    for ex in excludes:
        if not isinstance(ex, dict):
            problems.append({"rule": "MR010", "detail": "exclude entry is not a mapping"})
            continue
        unknown = [k for k in ex if k not in axes]
        if unknown:
            problems.append({"rule": "MR005", "exclude": ex,
                             "detail": f"exclude key(s) not in axes: {unknown}"})
        for k, v in ex.items():
            if k in axes and v not in axes[k]:
                problems.append({"rule": "MR011", "exclude": ex, "key": k, "value": v,
                                 "detail": f"exclude value {v!r} is not in axis {k!r}; "
                                           "this exclude can never match"})
        hit = [c for c in after if _matches(c, ex)]
        if not hit:
            problems.append({"rule": "MR002", "exclude": ex,
                             "detail": "exclude matches no combination"})
        after = [c for c in after if not _matches(c, ex)]
        removed += len(hit)

    includes = matrix.get("include") or []
    if not isinstance(includes, list):
        includes = []
        problems.append({"rule": "MR010", "detail": "include is not a list"})
    combos = [dict(c) for c in after]
    added = 0
    for inc in includes:
        if not isinstance(inc, dict):
            problems.append({"rule": "MR010", "detail": "include entry is not a mapping"})
            continue
        axis_part = {k: v for k, v in inc.items() if k in axes}
        extra = {k: v for k, v in inc.items() if k not in axes}
        for k, v in inc.items():
            if k in axes and v not in axes[k]:
                problems.append({
                    "rule": "MR003", "severity": "note", "include": inc, "key": k, "value": v,
                    "detail": f"include value {v!r} is not in axis {k!r}; "
                              "it will create an extra combination instead of extending the axis",
                })
        matched = [c for c in combos if _matches(c, axis_part)]
        if matched:
            for c in matched:
                c.update(inc)
        else:
            new = dict(inc)
            combos.append(new)
            added += 1
            if axis_part:
                problems.append({
                    "rule": "MR004", "severity": "note", "include": inc,
                    "detail": "include matches no base combination and becomes a new combination",
                })

    seen: dict[tuple, int] = {}
    for c in combos:
        key = json.dumps(c, sort_keys=True, default=str)
        seen[key] = seen.get(key, 0) + 1
    for key, n in seen.items():
        if n > 1:
            problems.append({"rule": "MR001", "combo": json.loads(key), "count": n,
                             "detail": f"duplicate expanded combination appears {n} times"})

    strategy = strategy or {}
    max_parallel = strategy.get("max-parallel")
    if isinstance(max_parallel, int) and max_parallel > len(combos):
        problems.append({"rule": "MR007", "severity": "note", "max_parallel": max_parallel,
                         "detail": f"max-parallel exceeds the {len(combos)} combinations (redundant, not harmful)"})
    ff = strategy.get("fail-fast")
    if ff is not None and not isinstance(ff, bool):
        problems.append({"rule": "MR008", "fail_fast": ff,
                         "detail": "fail-fast is not a boolean"})
    return MatrixResult(job, axes, base, after, combos, removed, added, problems)


def audit_workflow(doc: dict) -> list[MatrixResult]:
    out = []
    jobs = doc.get("jobs") if isinstance(doc, dict) else None
    if not isinstance(jobs, dict):
        return out
    for name, job in jobs.items():
        if not isinstance(job, dict):
            continue
        strategy = job.get("strategy")
        if isinstance(strategy, dict) and "matrix" in strategy:
            res = expand_matrix(name, strategy["matrix"], strategy)
            if not res.skipped:
                defined = set(res.axes)
                for inc in (strategy["matrix"].get("include") or []):
                    if isinstance(inc, dict):
                        defined.update(inc)
                for c in res.final:
                    defined.update(c)
                refs = set()
                import re
                refs.update(re.findall(r"matrix\.([A-Za-z_][A-Za-z0-9_-]*)", repr(job)))
                for key in sorted(refs - defined):
                    res.problems.append({"rule": "MR006", "key": key,
                                         "detail": f"matrix.{key} is referenced but never defined"})
            out.append(res)
    return out


def audit_workflow_text(text: str) -> list[MatrixResult]:
    import yaml
    doc = yaml.safe_load(text)
    return audit_workflow(doc)


def referenced_matrix_keys(doc: dict) -> set[str]:
    """Collect ``matrix.<name>`` references from the whole job body (best effort)."""
    import re
    hits = set()
    jobs = doc.get("jobs") if isinstance(doc, dict) else None
    if isinstance(jobs, dict):
        for job in jobs.values():
            hits.update(re.findall(r"matrix\.([A-Za-z_][A-Za-z0-9_-]*)", repr(job)))
    return hits
