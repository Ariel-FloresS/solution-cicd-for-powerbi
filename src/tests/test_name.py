from pbi_cicd.models import Item
from pbi_cicd.rules.name import check, suggest
 
WS: str = "WORKSPACE_1"

def test_valid_names_pass() -> None:
    """Letters, digits, underscore and hyphen, in the shapes the team
    actually uses."""
    items: list[Item] = [
        Item(f"{WS}/Sales_Monthly.Report"),
        Item(f"{WS}/VTA-Q1-2026.SemanticModel"),
        Item(f"{WS}/Budget2026.Report"),
    ]
 
    assert check(items) == []

def test_the_two_names_that_broke_the_pipeline() -> None:
    
    items: list[Item] = [
        Item(f"{WS}/Sales Report (1).Report"),
        Item(f"{WS}/Visualizacióñ.SemanticModel"),
    ]
 
    violations: list[tuple[Item, str]] = check(items)
 
    assert len(violations) == 2
    assert all(replacement for _, replacement in violations)


def test_accents_fold_to_their_base_letter() -> None:
    
    assert suggest("Análisis Ñoño") == "Analisis_Nono"
    assert suggest("Visualizatión Sales (1)") == "Visualization_Sales_1"

def test_a_name_with_nothing_to_keep_still_yields_a_suggestion() -> None:
    
    assert suggest("(((") != ""
 