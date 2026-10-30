"""Rules 4 to 6: validate the artefacts a pull request changed.

Exit codes: 0 every rule passed, 1 a rule found a problem, 2 a rule
could not run.
"""

from pathlib import Path
import argparse

from pbi_cicd.infrastructure.errors import PipelineError, RuleViolation
from pbi_cicd.infrastructure.output import annotate_error
from pbi_cicd.infrastructure.report import (
    FAILED, PASSED, PIPELINE_ERROR, labelled, section, write_section,
)
from pbi_cicd.models import ChangeSet, Finding, items_from_json
from pbi_cicd.rules import identity, name, sources

RULES = (name, identity, sources)

TITLE: str = "VALIDATE"


def main(argv: list[str] | None = None) -> int:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Rules 4 to 6: validate the artefacts a pull request changed."
    )
    parser.add_argument("--workspace", default="", help="Workspace folder, from the scope job.")
    parser.add_argument("--models", default="[]", help="JSON array of changed .SemanticModel paths.")
    parser.add_argument("--reports", default="[]", help="JSON array of changed .Report paths.")
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--report", type=Path, help="Where to write this job's report section.")
    args: argparse.Namespace = parser.parse_args(argv)

    try:
        changes: ChangeSet = ChangeSet(
            workspace=args.workspace or None,
            items=items_from_json(args.models) + items_from_json(args.reports),
        )
    except PipelineError as exc:
        annotate_error(exc)
        _publish(args.report, PIPELINE_ERROR, labelled("ERROR", exc))
        return exc.exit_code

    findings: list[Finding] = []
    broken: list[PipelineError] = []
    body: list[str] = []

    for rule in RULES:
        try:
            found: list[Finding] = rule.check(changes, args.repo_root)
        except PipelineError as exc:
            annotate_error(exc)
            broken.append(exc)
            body += [f"Rule {rule.RULE}: could not run"]
            continue

        findings += found
        body += [f"Rule {rule.RULE}: {len(found)} problem(s)" if found else f"Rule {rule.RULE}: passed"]

    body.append("")
    for finding in findings:
        violation: RuleViolation = RuleViolation(finding.rule, finding.message)
        annotate_error(violation, file=finding.file)
        body += labelled("ERROR", violation, finding.file)
    for exc in broken:
        body += labelled("ERROR", exc)

    if broken:
        _publish(args.report, PIPELINE_ERROR, body)
        return PipelineError.exit_code
    if findings:
        _publish(args.report, FAILED, body)
        return RuleViolation.exit_code

    _publish(args.report, PASSED, body)
    return 0


def _publish(report: Path | None, status: str, body: list[str]) -> None:
    text: str = section(TITLE, status, body)
    print(text)
    write_section(report, text)


if __name__ == "__main__":
    raise SystemExit(main())
