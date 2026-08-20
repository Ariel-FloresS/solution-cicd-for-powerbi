"""Rule 5: display names must be unique within a workspace
 
The name shown in Fabric comes from `displayName` inside `.platform`,
not from the folder. Two items of the same type carrying the same
display name collide when the workspace syncs, and Fabric refuses the
update with `PotentialDuplicateDisplayNameAndType`.
 
"""

from pbi_cicd.infrastructure.errors import PbiCicdError, PipelineError, RuleViolation
from pbi_cicd.infrastructure.output import annotate_error
from pbi_cicd.models import PLATFORM_FILE, Item
from collections import defaultdict
from pathlib import Path
import argparse
import json



RULE = "5"


def scan_workspace(workspace: str, repo_root: Path) -> dict[Item, str]:
    """Map every item in the workspace folder to its display name."""
    workspace_dir: Path = repo_root / workspace
 
    if not workspace_dir.is_dir():
        raise PipelineError(f"Workspace folder not found: {workspace}")
 
    names: dict[Item, str] = {}
 
    platform_path: Path
    for platform_path in sorted(workspace_dir.rglob(PLATFORM_FILE)):

        item: Item = Item(path=platform_path.parent.relative_to(repo_root).as_posix())

        names[item] = _read_display_name(platform_path)
 
    return names

def check(names: dict[Item, str]) -> list[list[Item]]:
    """Return each group of items sharing a display name and a type"""
    groups: dict[tuple[str, str], list[Item]] = defaultdict(list)
 
   
    for item, display_name in names.items():

        groups[(item.type, display_name)].append(item)
 
    return [
        sorted(members, key=lambda i: i.path)
        for members in groups.values()
        if len(members) > 1
    ]


def report(collisions: list[list[Item]], names: dict[Item, str]) -> None:

    """Annotate every item involved in a collision"""

    
    for members in collisions:
        display_name: str = names[members[0]]
        item: Item
        for item in members:
            others: str = ", ".join(o.name for o in members if o != item)
            annotate_error(
                RuleViolation(
                    RULE,
                    f"{item.type} {item.name!r} has display name "
                    f"{display_name!r}, which is also used by {others}. "
                    "Fabric refuses to update a workspace holding two items "
                    "of the same type with the same name. Rename one of them "
                    "in Power BI Desktop and export again.",
                ),
                file=f"{item.path}/{PLATFORM_FILE}",
            )


def _read_display_name(platform_path: Path) -> str:
    """Extract `metadata.displayName` from a `.platform` file."""
    try:
        raw: str = platform_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PipelineError(f"Could not read {platform_path}: {exc}") from exc
 
    try:
        content: dict = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PipelineError(f"{platform_path} is not valid JSON: {exc}") from exc
 
    display_name: str | None = content.get("metadata", {}).get("displayName")
 
    if not display_name:
        raise PipelineError(
            f"{platform_path} has no metadata.displayName. "
            "The file may be truncated or in an unsupported format."
        )
 
    return display_name

def _assert_no_collisions(collisions: list[list[Item]], names: dict[Item, str]) -> None:
    """Raise once with the summary, after every offender was annotated."""
    if not collisions:
        return
 
    
    listed: str = ", ".join(
        f"{members[0].type} {names[members[0]]!r}" for members in collisions
    )
    
    raise RuleViolation(
        RULE,
        f"{len(collisions)} display name(s) are used by more than one item of "
        f"the same type: {listed}. Rename one item per collision.",
    )

#### Orchestation

def main(argv: list[str] | None = None) -> int:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Rule 5: display names must be unique within a workspace."
    )
    parser.add_argument(
        "--workspace",
        required=True,
        help="Workspace folder to scan, from the scope job.",
    )
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    args: argparse.Namespace = parser.parse_args(argv)
 
    try:
        names: dict[Item, str] = scan_workspace(args.workspace, args.repo_root)

        collisions: list[list[Item]] = check(names)

        report(collisions, names)

        _assert_no_collisions(collisions, names)

    except PbiCicdError as exc:
        annotate_error(exc)
        return 1
 
    print(f"Checked {len(names)} display names in {args.workspace}, all unique.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())


    