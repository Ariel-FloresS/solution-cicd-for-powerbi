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
import sys


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