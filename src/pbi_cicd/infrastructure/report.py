"""Formatting shared by every section of the consolidated report.

Each command writes its own section as plain text. The gate only has to
put them in order.
"""
from pathlib import Path
from pbi_cicd.infrastructure.errors import PbiCicdError, PipelineError

WIDTH: int = 72
PASSED: str = "PASSED"
FAILED: str = "FAILED"
PIPELINE_ERROR: str = "PIPELINE ERROR"
# Width of the ERROR / WARNING label, continuation lines align under the text.
LABEL_WIDTH: int = 9

def banner(title: str, status: str) -> list[str]:
    """A section heading: the title on the left, its status on the right."""
    rule: str = "=" * WIDTH
    return [rule, f"{title:<52}{status:>20}", rule]

def status_of(error: PbiCicdError) -> str:
    """The section status a failure deserves."""
    return PIPELINE_ERROR if isinstance(error, PipelineError) else FAILED

def labelled(label: str, message: object, file: str | None = None) -> list[str]:
    """An ERROR or WARNING line, with multi-line messages kept aligned."""
    indent: str = " " * LABEL_WIDTH
    text: str = str(message).replace("\n", "\n" + indent)
    lines: list[str] = [f"{label:<{LABEL_WIDTH}}{text}"]
    if file:
        lines.append(f"{indent}file: {file}")
    return lines


def section(title: str, status: str, body: list[str]) -> str:
    return "\n".join([*banner(title, status), *body]).rstrip() + "\n"


def write_section(path: Path | None, text: str) -> None:
    """Save a section for the gate. A no-op when no path was given, as in local runs."""
    if path is not None:
        path.write_text(text, encoding="utf-8")
