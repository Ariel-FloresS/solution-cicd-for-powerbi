"""Unpack a dashboard zip delivered through the intake container.

Data Factory drops each dashboard as <prefix>/WORKSPACE/Name.zip and
dispatches the intake workflow with that path. The workflow downloads the
file; this command validates it and writes the two folders the Power BI
pipeline expects into a checkout of the target branch.

The path is the contract: its workspace segment says where the dashboard
goes, and its file name says what the dashboard is called.
"""

from pbi_cicd.infrastructure.errors import PipelineError
from pbi_cicd.infrastructure.output import annotate_error, set_outputs
from pbi_cicd.models import ITEM_SUFFIXES, Delivery
from pbi_cicd.rules.name import ALLOWED_NAME, suggest
from pathlib import Path, PurePosixPath
import argparse
import shutil
import zipfile


ZIP_SUFFIX: str = ".zip"
SKIPPED_PARTS: frozenset[str] = frozenset({"__macosx", ".ds_store", "thumbs.db", "desktop.ini"})
SKIPPED_FILES: frozenset[str] = frozenset({"cache.abf", "localsettings.json"})
SKIPPED_SUFFIXES: tuple[str, ...] = (".pbip",)




def locate(blob: str, prefix: str) -> tuple[str, str]:
    """The workspace and dashboard a blob path names: <prefix>/WORKSPACE/Name.zip."""
    parts: tuple[str, ...] = PurePosixPath(blob).parts

    if len(parts) != 3 or parts[0] != prefix or not parts[2].lower().endswith(ZIP_SUFFIX):
        raise PipelineError(
            f"{blob!r} does not follow {prefix}/WORKSPACE/Name.zip. The workspace "
            "segment says where the dashboard goes, so it cannot be missing or nested."
        )

    dashboard: str = PurePosixPath(parts[2]).stem

    if not ALLOWED_NAME.match(dashboard):
        raise PipelineError(
            f"Dashboard name {dashboard!r} uses characters that break the tools "
            f"downstream. Rename it to something like {suggest(dashboard)!r} and "
            "export again: the zip and its .Report and .SemanticModel folders "
            "must all use the new name."
        )

    return parts[1], dashboard


def plan(workspace: str, dashboard: str, names: list[str]) -> Delivery:
    """Decide where every file of the archive goes. Pure: reads only names.

    Tolerates a wrapper folder, as when a whole project folder was zipped,
    by anchoring each file at its .Report or .SemanticModel ancestor.
    """
    files: dict[str, str] = {}

    name: str
    for name in names:
        if name.endswith("/"):
            continue

        parts: tuple[str, ...] = PurePosixPath(name.replace("\\", "/")).parts
        if name.startswith(("/", "\\")) or ".." in parts:
            raise PipelineError(f"The zip contains an unsafe path: {name!r}.")

        if _skipped(parts):
            continue

        anchor: int | None = next(
            (i for i, part in enumerate(parts) if part.endswith(ITEM_SUFFIXES)), None
        )
        if anchor is None:
            continue

        files[name] = "/".join(parts[anchor:])

    found: set[str] = {path.split("/")[0] for path in files.values()}
    wanted: set[str] = {f"{dashboard}.Report", f"{dashboard}.SemanticModel"}

    if found != wanted:
        raise PipelineError(
            f"The zip must contain exactly {dashboard}.Report and {dashboard}.SemanticModel, "
            f"named like the zip. Found: {', '.join(sorted(found)) or 'neither'}."
        )

    return Delivery(workspace=workspace, dashboard=dashboard, files=files)


def extract(archive: zipfile.ZipFile, delivery: Delivery, target: Path) -> None:
    """Write the dashboard into the workspace, replacing any previous version.

    Replacing rather than overlaying: a page removed in the new version
    would otherwise survive from the old one.
    """
    workspace_dir: Path = target / delivery.workspace

    folder: str
    for folder in delivery.folders:
        shutil.rmtree(workspace_dir / folder, ignore_errors=True)

    name: str
    relative: str
    for name, relative in delivery.files.items():
        destination: Path = workspace_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(archive.read(name))


def _skipped(parts: tuple[str, ...]) -> bool:
    lowered: tuple[str, ...] = tuple(part.lower() for part in parts)
    return (
        any(part in SKIPPED_PARTS for part in lowered)
        or lowered[-1] in SKIPPED_FILES
        or lowered[-1].endswith(SKIPPED_SUFFIXES)
    )


def _write_report(path: Path | None, blob: str, status: str, lines: list[str]) -> None:
    rule: str = "=" * 72
    text: str = "\n".join([rule, f"{'INTAKE':<52}{status:>20}", rule, f"Zip: {blob}", *lines]) + "\n"
    print(text)
    if path is not None:
        path.write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Unpack a dashboard zip delivered through the intake container."
    )
    parser.add_argument("--blob", required=True, help="Path of the zip in the container, as intake/WORKSPACE/Name.zip.")
    parser.add_argument("--zip", type=Path, required=True, help="The downloaded zip file.")
    parser.add_argument("--prefix", default="intake", help="Folder of the container that receives the zips.")
    parser.add_argument("--target", type=Path, default=Path("."), help="Checkout of the target branch.")
    parser.add_argument("--report", type=Path, help="Where to write the intake report.")
    args: argparse.Namespace = parser.parse_args(argv)

    try:
        workspace, dashboard = locate(args.blob, args.prefix)

        if not (args.target / workspace).is_dir():
            raise PipelineError(
                f"Workspace folder {workspace} does not exist in the target branch. "
                "The intake folder must be named exactly like the repository folder."
            )

        with zipfile.ZipFile(args.zip) as archive:
            delivery: Delivery = plan(workspace, dashboard, archive.namelist())
            extract(archive, delivery, args.target)
    except (PipelineError, zipfile.BadZipFile) as exc:
        error: PipelineError = exc if isinstance(exc, PipelineError) else PipelineError(f"Not a valid zip: {exc}")
        annotate_error(error)
        _write_report(args.report, args.blob, "FAILED", [str(error)])
        return 1

    set_outputs({
        "workspace": delivery.workspace,
        "dashboard": delivery.dashboard,
        "slug": suggest(delivery.dashboard),
    })
    _write_report(args.report, args.blob, "PASSED", [
        f"Workspace: {delivery.workspace}",
        f"Dashboard: {delivery.dashboard}",
        f"Files:     {len(delivery.files)}",
    ])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())