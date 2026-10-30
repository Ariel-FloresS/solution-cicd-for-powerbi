from pathlib import Path

from pbi_cicd.models import ChangeSet, Finding, Item
from pbi_cicd.rules.name import ALLOWED_NAME, check, suggest
 
WS: str = "WORKSPACE_1"

def test_valid_names_pass() -> None:
    """Letters, digits, underscore and hyphen, in the shapes the team
    actually uses."""
    items: list[Item] = [
        Item(f"{WS}/Sales_Monthly.Report"),
        Item(f"{WS}/VTA-Q1-2026.SemanticModel"),
        Item(f"{WS}/Budget2026.Report"),
    ]
 
    assert check(ChangeSet(items=items), Path(".")) == []

def test_the_two_names_that_broke_the_pipeline() -> None:
    
    items: list[Item] = [
        Item(f"{WS}/Sales Report (1).Report"),
        Item(f"{WS}/Visualizacióñ.SemanticModel"),
    ]
 
    findings: list[Finding] = check(ChangeSet(items=items), Path("."))
 
    assert len(findings) == 2
    # The message carries the replacement, so the author knows what to use.
    assert "'Sales_Report_1'" in findings[0].message


def test_accents_fold_to_their_base_letter() -> None:
    
    assert suggest("Análisis Ñoño") == "Analisis_Nono"
    assert suggest("Visualizatión Sales (1)") == "Visualization_Sales_1"

def test_every_suggestion_passes_the_rule_it_resolves() -> None:
    """A suggestion the rule rejects sends the author in a circle.

    The fallback for a name with nothing to keep once had a space in it,
    and a check that only asked for a non-empty string let it through.
    """
    for name in ("(((", "Visualización_Ventas (1)", "Análisis Ñoño", "   ", "Sales Report"):
        assert ALLOWED_NAME.match(suggest(name)), name
