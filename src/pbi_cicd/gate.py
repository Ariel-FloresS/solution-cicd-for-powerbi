"""The pull request gate: merge when every job passed, report when one did not.

Exit codes: 0 every job passed, 1 at least one did not, 2 the gate
could not read the jobs' results.
"""

from pbi_cicd.infrastructure.errors import PipelineError
from pbi_cicd.infrastructure.report import banner
from pbi_cicd.infrastructure.output import annotate_error
from datetime import datetime, timezone
from pathlib import Path
import argparse
import json


# A skipped job is not a failure: with no semantic models changed the BPA
# never runs, and that is the correct outcome.
PASSING_RESULTS: frozenset[str] = frozenset({"success", "skipped"})

# Report sections in the order the jobs run, keyed by artifact name prefix.
SECTIONS: tuple[tuple[str, str], ...] = (
    ("report-scope", "scope"),
    ("report-validate", "validate_artefacts"),
    ("report-bpa", "bpa-rules"),
)


def failed_jobs(needs: dict) -> list[str]:
    """Jobs whose result blocks the merge."""
    return sorted(name for name, job in needs.items() if job["result"] not in PASSING_RESULTS)


def collect_sections(directory: Path) -> dict[str, str]:
    """Read every downloaded section, keyed by the artifact it came from.

    Each artifact downloads into a folder named after it, which is what
    tells one BPA section from another: they all hold a file with the
    same name.
    """
    if not directory.is_dir():
        return {}

    return {
        path.parent.name: path.read_text(encoding="utf-8", errors="replace")
        for path in sorted(directory.glob("*/*.txt"))
    }


def consolidate(
    needs: dict, sections: dict[str, str], pr: str, run_id: str, now: datetime
) -> str:
    """Build the failure report. Pure: the clock is passed in."""
    failed: list[str] = failed_jobs(needs)
    workspace: str = needs.get("scope", {}).get("outputs", {}).get("workspace") or "unknown"

    lines: list[str] = [
        f"PIPELINE REPORT - PR #{pr}",
        f"Workspace: {workspace}",
        f"Run {run_id} - {now:%Y-%m-%d %H:%M} UTC",
        f"Failed: {', '.join(failed)}",
        "",
    ]

    prefix: str
    job: str
    for prefix, job in SECTIONS:
        matching: list[str] = sorted(name for name in sections if name.startswith(prefix))
        result: str = needs.get(job, {}).get("result", "not run")

        if not matching and job in failed:
            lines += banner(job.upper(), result.upper())
            lines += [
                "This job failed without leaving a report: it stopped before",
                "producing one. The run log has the cause.",
                "",
            ]
            continue

        # Every command writes its section complete, heading included.
        lines += [sections[name].rstrip() + "\n" for name in matching]

    return "\n".join(lines)


def _parse_needs(raw: str) -> dict:
    try:
        needs: dict = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PipelineError(f"Expected the needs context as JSON, got {raw!r}") from exc

    if not needs:
        raise PipelineError("The needs context is empty: the gate has no jobs to evaluate.")
    return needs


def main(argv: list[str] | None = None) -> int:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Merge when every job passed; write the consolidated report when one did not."
    )
    parser.add_argument("--needs", required=True, help="toJSON(needs) from the calling workflow.")
    parser.add_argument("--sections", type=Path, required=True, help="Folder with the downloaded report sections.")
    parser.add_argument("--pr", required=True, help="Pull request number.")
    parser.add_argument("--run-id", required=True, help="Workflow run ID, for tracing the report back.")
    parser.add_argument("--output", type=Path, required=True, help="Where to write the consolidated report.")
    args: argparse.Namespace = parser.parse_args(argv)

    try:
        needs: dict = _parse_needs(args.needs)
    except PipelineError as exc:
        annotate_error(exc)
        return exc.exit_code

    failed: list[str] = failed_jobs(needs)
    if not failed:
        print(f"Every job passed: {', '.join(sorted(needs))}.")
        return 0

    report: str = consolidate(
        needs, collect_sections(args.sections), args.pr, args.run_id, datetime.now(timezone.utc)
    )
    args.output.write_text(report, encoding="utf-8")
    print(report)

    annotate_error(f"Not merged. Failed: {', '.join(failed)}. See the {args.output.stem} artifact.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
