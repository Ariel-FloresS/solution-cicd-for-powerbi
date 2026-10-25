"""
GitHub Actions output protocol.
 
The only module that knows how to talk to the runner. Rule modules
raise exceptions and return data; translating those into annotations
and job outputs happens here.
"""
 
from pbi_cicd.models import ChangeSet, Item
from typing import TextIO
import json
import os
import re
import sys


# A workflow command as the runner reads it: ::error file=path::message
COMMAND_RE: re.Pattern[str] = re.compile(
    r"^::(?P<level>error|warning|notice)(?P<properties>[^:]*)::(?P<message>.*)$"
)
FILE_RE: re.Pattern[str] = re.compile(r"file=([^,]+)")


def write_outputs(changes: ChangeSet) -> None:
    """Publish the detected scope as job outputs.
 
    Lists are serialized as JSON because `strategy.matrix` in the bpa
    job consumes them directly.
 
    Appends rather than overwrites: the runner reuses the same file
    across every step of a job.
    """
    target: str = os.environ.get("GITHUB_OUTPUT")
    if not target:
        return
 
    values: dict[str, str] = {
        "workspace": changes.workspace or "",
        "has_changes": str(changes.has_changes).lower(),
        "semantic_models": json.dumps([i.path for i in changes.semantic_models]),
        "reports": json.dumps([i.path for i in changes.reports]),
    }
 
    with open(target, "a", encoding="utf-8") as handle:
        key: str
        value: str
        for key, value in values.items():
            handle.write(f"{key}={value}\n")
 
def _escape(message: object) -> str:
    """
    Escape the characters the workflow command format Runner.
    """
    return (
        str(message)
        .replace("%", "%25")
        .replace("\r", "%0D")
        .replace("\n", "%0A")
    )

def annotate_warning(message: object, file: str | None = None) -> None:
    """
    Emit a warning visible in the pull request interface.
    """
    location: str = f" file={file}" if file else ""
    print(f"::warning{location}::{_escape(message)}", file=sys.stderr)



def annotate_error(message: object, file: str | None = None) -> None:
    """
    Emit an error visible in the pull request interface.
    """
    location: str = f" file={file}" if file else ""
    print(f"::error{location}::{_escape(message)}", file=sys.stderr)


def print_summary(changes: ChangeSet) -> None:
    """
    Log what was detected, for debugging a run that looks wrong.
    """
    if not changes.has_changes:
        print("No Power BI items changed.")
        return
 
    print(f"Workspace: {changes.workspace}")

    for item in changes.items:
        print(f"  {item.type:<14} {item.name}")


def plain_text(text: str) -> str:
    """Turn captured workflow commands back into readable lines.

    The report sections are copies of what each step printed, so their
    findings still carry the syntax and escaping meant for the runner.
    """
    lines: list[str] = []

    line: str
    for line in text.splitlines():
        match: re.Match[str] | None = COMMAND_RE.match(line)
        if match is None:
            lines.append(line)
            continue

        message: str = _unescape(match["message"]).replace("\n", "\n" + " " * 9)
        lines.append(f"{match['level'].upper():<9}{message}")

        location: re.Match[str] | None = FILE_RE.search(match["properties"])
        if location:
            lines.append(f"{'':<9}file: {location[1]}")

    return "\n".join(lines)


def _unescape(message: str) -> str:
    """Undo `_escape`. `%25` goes last, since it was escaped first."""
    return message.replace("%0D", "\r").replace("%0A", "\n").replace("%25", "%")