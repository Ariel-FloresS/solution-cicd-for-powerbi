"""Rules 1 to 3: pull request scope.
 
  1. One workspace per pull request.
  2. Several dashboards allowed as long as they share a workspace.
  3. Only modified items are processed.
 
Produces the ChangeSet every other rule module and job consumes. If
this module resolves the wrong set, everything downstream validates
the wrong thing.
"""


import argparse
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
 
from pbi_cicd.infrastructure.output import annotate_error, write_outputs, print_summary, annotate_warning
from pbi_cicd.infrastructure.git import changed_files,deleted_files
from pbi_cicd.infrastructure.errors import PipelineError, RuleViolation, PbiCicdError
from pbi_cicd.models import ITEM_SUFFIXES, ChangeSet, Item


# Identity file Power BI Desktop writes inside every item folder.
PLATFORM_FILE: str = ".platform"
 
# Top-level folders that are not business domains.
NON_WORKSPACE_DIRS: frozenset[str] = frozenset({"src", ".github", ".git"})

# Depth 2 means a file sitting directly under a workspace folder,
# such as ventas/.gitignore. Those are legitimate and carry no item.
WORKSPACE_FILE_DEPTH: int = 2


def resolve(paths: Iterable[str]) -> ChangeSet:
    """Map changed file paths to the Fabric items that contain them"""
    workspaces: set[str] = set()
    items: set[Item] = set()
    unmapped: list[str] = []
 
    for raw in paths:
        parts: tuple[str, ...] = PurePosixPath(raw).parts
 
        # File at the repository root.
        if len(parts) < WORKSPACE_FILE_DEPTH:
            continue
 
        # Top-level folder that is not a business domain.
        if parts[0] in NON_WORKSPACE_DIRS:
            continue
 
        workspaces.add(parts[0])
 
        item: Item | None = _find_item_ancestor(parts)
        if item is None:
            # A file directly under the workspace is fine. Anything
            # deeper should have landed inside an item folder, so
            # failing to map it means the logic broke.
            if len(parts) > WORKSPACE_FILE_DEPTH:
                unmapped.append(raw)
            continue
 
        items.add(item)
 
    _assert_single_workspace(workspaces)
    _assert_nothing_lost(unmapped, items)
 
    return ChangeSet(
        workspace=next(iter(workspaces), None),
        items=sorted(items, key=lambda i: (i.type, i.path)),
    )
 
 
def resolve_removed(paths: Iterable[str]) -> list[Item]:
    """Map deleted file paths to the items they belonged to"""
    removed: set[Item] = set()
 
    for raw in paths:
        parts: tuple[str, ...] = PurePosixPath(raw).parts
 
        if len(parts) < WORKSPACE_FILE_DEPTH or parts[0] in NON_WORKSPACE_DIRS:
            continue
 
        item: Item | None = _find_item_ancestor(parts)
        if item is not None:
            removed.add(item)
 
    return sorted(removed, key=lambda i: (i.type, i.path))
 
 
def warn_removed(removed: list[Item]) -> None:
    """Surface deletions on the pull request without blocking it"""
    if not removed:
        return
 
    item: Item
    for item in removed:
        annotate_warning(
            f"{item.type} {item.name!r} was removed or renamed in "
            f"workspace {item.workspace!r}. It will disappear from the "
            "workspace on the next update from Git.",
        )
 
 
def verify(changes: ChangeSet, repo_root: Path) -> None:
    """Confirm every resolved item exists on disk and is a real item"""

    item: Item
    for item in changes.items:
        item_dir: Path = repo_root / item.path
 
        if not item_dir.is_dir():
            raise PipelineError(f"Resolved item does not exist on disk: {item.path}")
 
        if not (item_dir / PLATFORM_FILE).is_file():
            raise PipelineError(
                f"Folder {item.path} has no {PLATFORM_FILE}. "
                "It is not a valid Fabric item."
            )
 
 
def _find_item_ancestor(parts: tuple[str, ...]) -> Item | None:
    """Return the ancestor folder that is a Fabric item, if any."""
    index: int
    segment: str
    for index, segment in enumerate(parts):
        if segment.endswith(ITEM_SUFFIXES):
            return Item(path="/".join(parts[: index + 1]))
    return None
 
 
def _assert_single_workspace(workspaces: set[str]) -> None:
    """Rule 1."""
    if len(workspaces) > 1:
        listed: str = ", ".join(sorted(workspaces))
        raise RuleViolation(
            "1",
            f"A pull request may only touch one workspace. Found "
            f"{len(workspaces)}: {listed}. Split this into separate "
            "pull requests.",
        )
 
 
def _assert_nothing_lost(unmapped: list[str], items: set[Item]) -> None:
    """Refuse to report an empty scope when files clearly changed"""

    if unmapped and not items:
        listed: str = "\n  ".join(sorted(unmapped))
        raise PipelineError(
            "Files changed under a workspace folder but no item could be "
            f"resolved. Unmapped paths:\n  {listed}"
        )
 
 
def main(argv: list[str] | None = None) -> int:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Rules 1 to 3: resolve the scope of a pull request."
    )
    parser.add_argument(
        "--base",
        required=True,
        help="Comparison ref: origin/main on a PR, HEAD~1 on main.",
    )
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    args: argparse.Namespace = parser.parse_args(argv)
 
    try:
        changes: ChangeSet = resolve(changed_files(args.base, args.repo_root))
        verify(changes, args.repo_root)
        removed: list[Item] = resolve_removed(
            deleted_files(args.base, args.repo_root)
        )
    except PbiCicdError as exc:
        annotate_error(exc)
        return 1
 
    warn_removed(removed)
    write_outputs(changes)
    print_summary(changes)
    return 0
 
 
if __name__ == "__main__":
    raise SystemExit(main())