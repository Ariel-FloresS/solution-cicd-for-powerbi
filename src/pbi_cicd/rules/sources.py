"""Rule 6: semantic models must not read from local paths
 
A file sitting on someone's laptop works in Power BI Desktop and fails
on the first refresh in the service. 
"""

from pbi_cicd.infrastructure.errors import PbiCicdError, PipelineError, RuleViolation
from pbi_cicd.infrastructure.output import annotate_error
from pbi_cicd.models import Item
from pathlib import Path
import argparse
import json
import re


RULE:str = "6"
 
# Where the model definition lives inside a .SemanticModel folder.
DEFINITION_DIR:str = "definition"
TMDL_GLOB: str = "*.tmdl"

# Patterns that can only point at a machine, never at the service.
LOCAL_PATH_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # C:\ or C:/ — a Windows drive letter.
    ("Windows drive path", re.compile(r"\b[A-Za-z]:[\\/]")),
    # file:/// — a local file URI.
    ("local file URI", re.compile(r"file:///", re.IGNORECASE)),
    # /Users/ or /home/ — a macOS or Linux home directory.
    ("home directory path", re.compile(r"/(?:Users|home)/[A-Za-z0-9._-]+/")),
)



def scan_model(model: Item, repo_root: Path) -> list[tuple[Path, str, str]]:
    """Return every local path found in a semantic model's TMDL files"""

    definition: Path = repo_root / model.path / DEFINITION_DIR
 
    if not definition.is_dir():
        raise PipelineError(
            f"{model.path} has no {DEFINITION_DIR} folder. "
            "The semantic model export looks incomplete."
        )
 
    findings: list[tuple[Path, str, str]] = []
 
    tmdl_path: Path
    for tmdl_path in sorted(definition.rglob(TMDL_GLOB)):
        findings.extend(
            (tmdl_path, label, line)
            for label, line in find_local_paths(_read(tmdl_path))
        )
 
    return findings


def find_local_paths(text: str) -> list[tuple[str, str]]:
    """Return the kind of local path and the line carrying it"""
    findings: list[tuple[str, str]] = []
 
    for line in text.splitlines():
        label: str
        pattern: re.Pattern[str]
        for label, pattern in LOCAL_PATH_PATTERNS:
            if pattern.search(line):
                findings.append((label, line.strip()))
                break
 
    return findings


def report(model: Item, findings: list[tuple[Path, str, str]], repo_root: Path) -> None:
    """Annotate each local path against the file that carries it."""
    
    for tmdl_path, label, line in findings:
        relative: str = tmdl_path.relative_to(repo_root).as_posix()
        annotate_error(
            RuleViolation(
                RULE,
                f"{model.name} reads from a {label}: {_truncate(line)} "
                "A path on a local machine does not exist in the Fabric "
                "service, so the refresh fails and the dashboard shows up "
                "broken. Move the data to SharePoint, Snowflake or a Delta table. ",
            ),
            file=relative,
        )

def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PipelineError(f"Could not read {path}: {exc}") from exc
 
 
def _truncate(line: str, limit: int = 120) -> str:
    """Keep annotations readable when an M query runs long."""
    return line if len(line) <= limit else f"{line[:limit]}..."
 
 
def _parse_models(raw: str) -> list[Item]:
    """Turn a JSON array emitted by the scope job into items."""
    try:
        paths: list[str] = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PipelineError(f"Expected a JSON array, got {raw!r}") from exc
 
    return [Item(path=path) for path in paths]
 
 
def _assert_no_findings(total: int, models: int) -> None:
    """Raise once with the summary, after every path was annotated."""
    if not total:
        return
 
    raise RuleViolation(
        RULE,
        f"Found {total} local path reference(s) across {models} semantic "
        "model(s). Every source must be reachable from the Fabric service (No local source Connection). ",
    )


def main(argv: list[str] | None = None) -> int:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Rule 6: semantic models must not read from local paths."
    )
    parser.add_argument(
        "--models",
        default="[]",
        help="JSON array of changed .SemanticModel paths, from the scope job.",
    )
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    args: argparse.Namespace = parser.parse_args(argv)
 
    try:
        models: list[Item] = _parse_models(args.models)
        total: int = 0
 
        model: Item
        for model in models:
            findings: list[tuple[Path, str, str]] = scan_model(model, args.repo_root)
            report(model, findings, args.repo_root)
            total += len(findings)
 
        _assert_no_findings(total, len(models))
    except PbiCicdError as exc:
        annotate_error(exc)
        return 1
 
    print(f"Checked {len(models)} semantic model(s), no local paths found.")
    return 0
 
 
if __name__ == "__main__":
    raise SystemExit(main())