"""Rule 4: item folder names must use safe characters"""

from pbi_cicd.infrastructure.errors import PbiCicdError, RuleViolation, PipelineError
from pbi_cicd.infrastructure.output import annotate_error
from pbi_cicd.models import Item, PLATFORM_FILE
import unicodedata
import argparse
import json
import re

# ASCII letters, digits, underscore and hyphen. No dots: the type is
# derived by splitting on the last dot, and a name containing one
# makes that fragile to read for no gain.

ALLOWED_NAME: re.Pattern = re.compile(r"^[A-Za-z0-9_-]+$")

RULE: str = "4"

def suggest(name: str) -> str:
    """Turn a rejected name into an accepted one"""

    # NFKD splits an accented (á,é,í,ó,ú, ñ) letter into base letter plus combining
    # mark; encoding to ASCII then drops the marks.
    folded: str = (
        unicodedata.normalize("NFKD", name)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
 
    cleaned: str = re.sub(r"[^A-Za-z0-9_-]+", "_", folded).strip("_")
 
    return cleaned or "renamed item"

def check(items: list[Item]) -> list[tuple[Item, str]]:
    """Return one entry per item whose name uses forbidden characters"""

    violations: list[tuple[Item, str]] = []
    
    for item in items:
        if not ALLOWED_NAME.match(item.name):
            violations.append((item, suggest(item.name)))
 
    return violations



def report(violations: list[tuple[Item, str]]) -> None:
    """Annotate each violation against the folder that carries it"""

    for item, proposal in violations:
        annotate_error(
            RuleViolation(
                RULE,
                f"{item.type} folder {item.name!r} uses characters that break "
                f"the tools downstream. Rename it in Power BI Desktop to "
                f"something like {proposal!r}. The name business users see "
                f"comes from displayName in .platform and is unaffected.",
            ),
            file=f"{item.path}/{PLATFORM_FILE}",
        )

def _assert_no_violations(violations: list[tuple[Item, str]], total: int) -> None:
    """Raise once with the summary, after every offender was annotated."""
    if not violations:
        return
 
    names: str = ", ".join(repr(item.name) for item, _ in violations)

    raise RuleViolation(
        RULE,
        f"{len(violations)} of {total} item names use forbidden characters: "
        f"{names}. Allowed: ASCII letters, digits, underscore and hyphen.",
    )

def _parse_items(raw: str) -> list[Item]:
    """Turn a JSON array emitted by the scope job into items."""
    try:
        paths: list[str] = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PipelineError(f"Expected a JSON array, got {raw!r}") from exc
 
    return [Item(path=path) for path in paths]

## Orchestation

def main(argv: list[str] | None = None) -> int:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Rule 11: item folder names must use safe characters."
    )
    parser.add_argument(
        "--models",
        default="[]",
        help="JSON array of changed .SemanticModel paths, from the scope job.",
    )
    parser.add_argument(
        "--reports",
        default="[]",
        help="JSON array of changed .Report paths, from the scope job.",
    )
    args: argparse.Namespace = parser.parse_args(argv)
 
    try:
        items: list[Item] = _parse_items(args.models) + _parse_items(args.reports)

        violations: list[tuple[Item, str]] = check(items)

        report(violations)

        _assert_no_violations(violations, len(items))

    except PbiCicdError as exc:
        annotate_error(exc)
        return 1
 
    print(f"Checked {len(items)} item names, all valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


