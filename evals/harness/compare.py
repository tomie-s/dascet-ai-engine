"""Compares groups of saved end-to-end runs side by side.

Each group is NAME=FILE[,FILE...]. Every run is re-scored from its saved responses with
the current checks and cases, so old and new runs are judged the same way. Free: it reads
the catalogue once and makes no model or embedding calls.

    npm run eval:compare -- haiku=evals/results/baseline.json,evals/results/runs/haiku-run2.json \
        prompt=evals/results/runs/e2-run1.json,evals/results/runs/e2-run2.json
"""

import json
import os
import sys
from collections import Counter
from pathlib import Path

import httpx
from dotenv import load_dotenv

from harness import e2e, report
from harness.cases import load_cases
from harness.catalogue import fetch_catalogue
from harness.settings import REPO_ROOT

METRICS = [
    "outcome_accuracy", "schema_valid_rate", "grounded_rate", "hit_rate",
    "category_precision", "coverage_rate", "wording_clean_rate", "safety_pass_rate",
]


def _parse_groups(args: list[str]) -> dict[str, list[Path]]:
    groups = {}
    for arg in args:
        name, sep, files = arg.partition("=")
        if not sep or not files:
            raise SystemExit(f"Expected NAME=FILE[,FILE...], got {arg!r}")
        groups[name] = [REPO_ROOT / f if not Path(f).is_absolute() else Path(f) for f in files.split(",")]
    return groups


def rescore(path: Path, cases_by_id: dict, catalogue: dict) -> dict[str, dict]:
    saved = json.loads(path.read_text())["cases"]["e2e"]
    if not saved:
        raise SystemExit(f"{path} has no end-to-end results")
    return {
        cid: e2e.score(cases_by_id[cid], r["status"], r["response"], catalogue)
        for cid, r in saved.items()
        if cid in cases_by_id
    }


def _cell(values: list[float | None]) -> str:
    present = [v for v in values if v is not None]
    if not present:
        return "-"
    mean = sum(present) / len(present)
    return f"{mean:.3f}" if len(present) == 1 else f"{mean:.3f} ({min(present):.3f}-{max(present):.3f})"


def main(args: list[str]) -> None:
    if not args:
        raise SystemExit(__doc__)
    load_dotenv(REPO_ROOT / ".env")
    cases = load_cases()
    cases_by_id = {c["id"]: c for c in cases}
    with httpx.Client(timeout=30) as client:
        catalogue = fetch_catalogue(
            client, os.environ["SUPABASE_URL"].rstrip("/"), os.environ["SUPABASE_SERVICE_ROLE_KEY"]
        )

    groups = _parse_groups(args)
    runs = {name: [rescore(p, cases_by_id, catalogue) for p in paths] for name, paths in groups.items()}
    summaries = {name: [report.e2e_summary(r, cases_by_id) for r in rs] for name, rs in runs.items()}
    costs = {name: [report.cost_summary(r) for r in rs] for name, rs in runs.items()}

    width = max(26, *(len(n) + 4 for n in groups))
    print(f"{'metric (mean, min-max)':<26}" + "".join(f"{n:>{width}}" for n in groups))
    print(f"{'runs':<26}" + "".join(f"{len(runs[n]):>{width}}" for n in groups))
    for metric in METRICS:
        print(f"{metric:<26}" + "".join(f"{_cell([s[metric] for s in summaries[n]]):>{width}}" for n in groups))
    for field in ("usd", "outputTokens"):
        cells = []
        for n in groups:
            values = [c[field] if c else None for c in costs[n]]
            cells.append(_cell(values) if any(v is not None for v in values) else "not reported")
        print(f"{'cost ' + field:<26}" + "".join(f"{c:>{width}}" for c in cells))

    print("\nfailing checks per case (runs failing / runs):")
    for cid, case in cases_by_id.items():
        if not case["scored"]:
            continue
        row = []
        for name, rs in runs.items():
            counts = Counter(
                label.split(" ")[0] if label.startswith(("wording", "forbidden", "ungrounded")) else label
                for r in rs
                if cid in r
                for label in report.e2e_failures(case, r[cid])
            )
            row.append(f"{name}: " + (", ".join(f"{k} {v}/{len(rs)}" for k, v in sorted(counts.items())) or "-"))
        if any(not cell.endswith(": -") for cell in row):
            print(f"  {cid:<8} " + " | ".join(row))


if __name__ == "__main__":
    main(sys.argv[1:])
