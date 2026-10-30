"""Rule 5: display names must be unique within a workspace
 
The name shown in Fabric comes from `displayName` inside `.platform`,
not from the folder. Two items of the same type carrying the same
display name collide when the workspace syncs, and Fabric refuses the
update with `PotentialDuplicateDisplayNameAndType`.
 
"""

from pbi_cicd.models import PLATFORM_FILE, ChangeSet, Finding, Item
from pbi_cicd.infrastructure.errors import PipelineError
from collections import defaultdict
from pathlib import Path
import json

RULE: str = "5"


def check(changes: ChangeSet, repo_root: Path) -> list[Finding]:
    if not changes.workspace:
        return []

    names: dict[Item, str] = scan_workspace(changes.workspace, repo_root)
    findings: list[Finding] = []

    group: list[Item]
    for group in find_collisions(names):
        item: Item
        for item in group:
            others: str = ", ".join(other.name for other in group if other != item)
            findings.append(Finding(
                rule=RULE,
                file=f"{item.path}/{PLATFORM_FILE}",
                message=(
                    f"{item.type} {item.name!r} has display name {names[item]!r}, "
                    f"which is also used by {others}. Fabric refuses to update a "
                    "workspace holding two items of the same type with the same "
                    "name. Rename one of them in Power BI Desktop and export again."
                ),
            ))

    return findings


def find_collisions(names: dict[Item, str]) -> list[list[Item]]:
    """Each group of items sharing a display name and a type.

    The type is part of the key on purpose: Power BI Desktop names a
    report and its semantic model the same, and that is not a collision.
    """
    groups: dict[tuple[str, str], list[Item]] = defaultdict(list)

    item: Item
    display_name: str
    for item, display_name in names.items():
        groups[(item.type, display_name)].append(item)

    return [
        sorted(members, key=lambda i: i.path)
        for members in groups.values()
        if len(members) > 1
    ]


def scan_workspace(workspace: str, repo_root: Path) -> dict[Item, str]:
    """Map every item in the workspace folder to its display name."""
    workspace_dir: Path = repo_root / workspace
    if not workspace_dir.is_dir():
        raise PipelineError(f"Workspace folder not found: {workspace}")

    return {
        Item(path=platform.parent.relative_to(repo_root).as_posix()): _read_display_name(platform)
        for platform in sorted(workspace_dir.rglob(PLATFORM_FILE))
    }


def _read_display_name(platform: Path) -> str:
    try:
        content: dict = json.loads(platform.read_text(encoding="utf-8"))
    except OSError as exc:
        raise PipelineError(f"Could not read {platform}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise PipelineError(f"{platform} is not valid JSON: {exc}") from exc

    display_name: str | None = content.get("metadata", {}).get("displayName")
    if not display_name:
        raise PipelineError(
            f"{platform} has no metadata.displayName. "
            "The file may be truncated or in an unsupported format."
        )
    return display_name
