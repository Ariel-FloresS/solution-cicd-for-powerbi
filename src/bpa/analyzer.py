"""Run Tabular Editor 2 over a model and turn its output into violations.

Knows nothing about points or levels: it only reports which rules each
object broke, and which rules failed to evaluate.
"""
from pbi_cicd.infrastructure.errors import PipelineError
from pathlib import Path
import subprocess
import re

MODEL_DEFINITION: Path = Path("definition") / "model.tmdl"

# Printed only once Tabular Editor has loaded the model and started evaluating.
START_MARKER: str = "Running Best Practice Analyzer..."

#Regular Expressions look for error or Warning in tabular output.
VIOLATION_RE: re.Pattern[str] = re.compile(
    r'^(?:(?:::(?:error|warning)::|Error:|Warning:)\s*)?'
    r'(?P<object>.+?) violates rule "(?P<rule>[^"]+)"\s*$'
)
RULE_ERROR_RE: re.Pattern[str] = re.compile(
    r"^(?:::error::\s*)?Error on rule '(?P<rule>[^']+)': (?P<message>.*)$"
)

TIMEOUT_SECONDS: int = 600


def run_analyzer(exe: Path, definition: Path, rules_file: Path, output: Path) -> str:
    """Run Tabular Editor and return everything it printed.

    TabularEditor.exe is a GUI-subsystem binary: called directly it returns
    at once and keeps writing in the background, so the runner kills it
    mid-analysis. `start /WAIT` is what Tabular Editor's documentation
    prescribes to block until it finishes.
    """
    command: str = (
        f'start "" /B /WAIT "{exe}" "{definition}" -A "{rules_file}" > "{output}" 2>&1'
    )

    try:
        subprocess.run(command, shell=True, timeout=TIMEOUT_SECONDS, check=False)
    except subprocess.TimeoutExpired as exc:
        raise PipelineError(
            f"Tabular Editor did not finish within {TIMEOUT_SECONDS} seconds."
        ) 

    try:
        return output.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        raise PipelineError(f"Could not read the analyzer output at {output}: {exc}") 


def parse(text: str) -> tuple[dict[str, list[str]], dict[str, str]]:
    """The objects violating each rule, and the rules that failed to evaluate."""
    if START_MARKER not in text:
        raise PipelineError(
            f'The analyzer output lacks "{START_MARKER}": Tabular Editor never '
            "evaluated the model, so its silence cannot be read as a pass."
        )

    violations: dict[str, list[str]] = {}
    rule_errors: dict[str, str] = {}

    line: str
    for line in text.splitlines():
        line = line.strip()

        if match := VIOLATION_RE.match(line):
            violations.setdefault(match["rule"], []).append(match["object"])
        elif match := RULE_ERROR_RE.match(line):
            rule_errors[match["rule"]] = match["message"]

    return violations, rule_errors
