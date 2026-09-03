from pbi_cicd.models import Item
from pbi_cicd.rules.identity import check
 
WS: str = "WORKSPACE_1"

def test_report_and_model_sharing_a_name_is_not_a_collision() -> None:
    
    collisions: list[list[Item]] = check({
        Item(f"{WS}/Sales.Report"): "Sales Report",
        Item(f"{WS}/Sales.SemanticModel"): "Sales Report",
    })
 
    assert collisions == []


def test_two_reports_with_the_same_display_name_collide() -> None:
    
    collisions: list[list[Item]] = check({
        Item(f"{WS}/Sales_Monthly.Report"): "Sales Report",
        Item(f"{WS}/Sales_Quarterly.Report"): "Sales Report",
    })
 
    assert len(collisions) == 1
    assert {item.path for item in collisions[0]} == {
        f"{WS}/Sales_Monthly.Report",
        f"{WS}/Sales_Quarterly.Report",
    }