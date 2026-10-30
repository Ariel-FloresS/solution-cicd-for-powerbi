"""Rule 6: semantic models must not read from local paths
 
A file sitting on someone's laptop works in Power BI Desktop and fails
on the first refresh in the service. 
"""


from pbi_cicd.infrastructure.errors import PipelineError
from pbi_cicd.models import ChangeSet, Finding
from pathlib import Path
import re

RULE: str = "6"

DEFINITION_DIR: str = "definition"

# Patterns that can only point at a machine, never at the service.
LOCAL_PATH_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Windows drive path", re.compile(r"\b[A-Za-z]:[\\/]")),
    ("local file URI", re.compile(r"file:///", re.IGNORECASE)),
    ("home directory path", re.compile(r"/(?:Users|home)/[A-Za-z0-9._-]+/")),
)

MAX_LINE_LENGTH: int = 120


def check(changes: ChangeSet, repo_root: Path) -> list[Finding]:
    findings: list[Finding] = []

    for model in changes.semantic_models:
        definition: Path = repo_root / model.path / DEFINITION_DIR
        if not definition.is_dir():
            raise PipelineError(
                f"{model.path} has no {DEFINITION_DIR} folder. "
                "The semantic model export looks incomplete."
            )

        # Every .tmdl, not only tables/: shared queries and parameters
        # live in expressions.tmdl, and that is where a path often hides.
        tmdl: Path
        for tmdl in sorted(definition.rglob("*.tmdl")):
            label: str
            line: str
            for label, line in find_local_paths(_read(tmdl)):
                findings.append(Finding(
                    rule=RULE,
                    file=tmdl.relative_to(repo_root).as_posix(),
                    message=(
                        f"{model.name} reads from a {label}: {_truncate(line)} "
                        "A path on a local machine does not exist in the Fabric "
                        "service, so the refresh fails and the dashboard shows up "
                        "broken. Move the data to SharePoint, Snowflake or a Delta table."
                    ),
                ))

    return findings


def find_local_paths(text: str) -> list[tuple[str, str]]:
    """The kind of local path and the line carrying it, once per line."""
    findings: list[tuple[str, str]] = []

    line: str
    for line in text.splitlines():
        label: str
        pattern: re.Pattern[str]
        for label, pattern in LOCAL_PATH_PATTERNS:
            if pattern.search(line):
                findings.append((label, line.strip()))
                break

    return findings


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PipelineError(f"Could not read {path}: {exc}") from exc


def _truncate(line: str) -> str:
    return line if len(line) <= MAX_LINE_LENGTH else f"{line[:MAX_LINE_LENGTH]}..."
