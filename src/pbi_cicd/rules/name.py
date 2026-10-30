"""Rule 4: item folder names use only ASCII letters, digits, _ and -."""

from pathlib import Path
import re
import unicodedata

from pbi_cicd.models import PLATFORM_FILE, ChangeSet, Finding

RULE: str = "4"

# No dots: the item type is the text after the last dot, so a dot in the
# name makes that fragile to read for no gain.
ALLOWED_NAME: re.Pattern[str] = re.compile(r"^[A-Za-z0-9_-]+$")


def check(changes: ChangeSet, repo_root: Path) -> list[Finding]:
    return [
        Finding(
            rule=RULE,
            file=f"{item.path}/{PLATFORM_FILE}",
            message=(
                f"{item.type} folder {item.name!r} uses characters that break "
                f"the tools downstream. Rename it in Power BI Desktop to "
                f"something like {suggest(item.name)!r}."
            ),
        )
        for item in changes.items
        if not ALLOWED_NAME.match(item.name)
    ]


def suggest(name: str) -> str:
    """Turn a rejected name into one this rule accepts.

    NFKD splits an accented letter into its base letter plus a combining
    mark; encoding to ASCII then drops only the mark, so `Análisis`
    becomes `Analisis` instead of losing the vowel.
    """
    folded: str = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    cleaned: str = re.sub(r"[^A-Za-z0-9_-]+", "_", folded).strip("_")
    return cleaned or "renamed_item"
