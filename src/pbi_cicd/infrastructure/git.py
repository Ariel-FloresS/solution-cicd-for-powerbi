"""
Git access.
 
The only module that invokes the git binary. Every git failure is
translated into `PipelineError`.
"""
from .errors import PipelineError
from pathlib import Path
import subprocess

def run(args: list[str], repo_root: Path) -> str:
    """
    Invoke git and return its standard output.
    """
    try:
        completed: subprocess.CompletedProcess[str] = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as exc:
        raise PipelineError("The git executable was not found.") from exc

    except subprocess.CalledProcessError as exc:
        detail: str = exc.stderr.strip() or f"exit code {exc.returncode}"
        raise PipelineError(f"git {' '.join(args)} has failed --->: {detail}") from exc
 
    return completed.stdout


def assert_ref_exists(ref: str, repo_root: Path) -> None:
    """Fail loudly when `ref` is not present in the local clone.
 
    `actions/checkout` fetches a single commit by default, so main is
    not downloaded. Diffing against a missing ref yields an empty
    result, which is indistinguishable from "nothing changed" — the
    pull request would pass green without validating anything.
 
    The `^{commit}` suffix asks git to resolve the ref all the way to
    a commit object, so a name that exists but whose object was never
    fetched still fails.
    """
    try:
        run(["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], repo_root)
    except PipelineError as exc:
        raise PipelineError(
            f"Reference {ref!r} was not found in the local clone. "
            "Check that actions/checkout uses fetch-depth: 0."
        ) from exc

def _diff(base_ref: str, repo_root: Path, diff_filter: str) -> list[str]:
    """Run a name-only diff against the merge base"""
    assert_ref_exists(base_ref, repo_root)
 
    output: str = run(
        ["diff", "--name-only", f"--diff-filter={diff_filter}", f"{base_ref}...HEAD"],
        repo_root,
    )
    return [line for line in output.splitlines() if line.strip()]


def changed_files(base_ref: str, repo_root: Path) -> list[str]:
    """Return paths modified relative to `base_ref`.
 
    `--diff-filter=d` drops deletions: a file that no longer exists
    cannot be validated.
    """
    assert_ref_exists(base_ref, repo_root)
 
    output: str = run(
        ["diff", "--name-only", "--diff-filter=d", f"{base_ref}...HEAD"],
        repo_root,
    )
    return [line for line in output.splitlines() if line.strip()]

def deleted_files(base_ref: str, repo_root: Path) -> list[str]:
    """Return paths removed relative to `base_ref`"""
    return _diff(base_ref, repo_root, diff_filter="D")

