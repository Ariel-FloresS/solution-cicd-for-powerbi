from pbi_cicd.infrastructure.errors import PipelineError, RuleViolation
from pbi_cicd.models import  ChangeSet, Item
from pbi_cicd.rules.scope import resolve, resolve_removed
import pytest

WS : str= "WORKSPACE_1"
OTHER_WS: str = "WORKSPACE_2"


def paths_of(changes: ChangeSet) -> set[str]:
    return {item.path for item in changes.items}

def test_several_files_in_one_item_resolve_to_one_item() -> None:
    """Editing a measure touches several files in the same folder.
 
    They must collapse into one item, or the BPA matrix would spawn a
    Windows runner per file instead of per model.
    """
    changes: ChangeSet = resolve([
        f"{WS}/Sales.SemanticModel/definition/tables/Sales.tmdl",
        f"{WS}/Sales.SemanticModel/definition/model.tmdl",
        f"{WS}/Sales.SemanticModel/.platform",
    ])
 
    assert paths_of(changes) == {f"{WS}/Sales.SemanticModel"}


def test_two_workspaces_raise() -> None:
    """Rule 1. Both names belong in the message: the author needs to
    know which second workspace they touched."""
    with pytest.raises(RuleViolation) as exc:
        resolve([
            f"{WS}/Sales.Report/definition.pbir",
            f"{OTHER_WS}/Budget.Report/definition.pbir",
        ])
 
    assert WS in str(exc.value)
    assert OTHER_WS in str(exc.value)


def test_two_dashboards_in_one_workspace_pass() -> None:
    
    changes: ChangeSet = resolve([
        f"{WS}/Sales.Report/definition.pbir",
        f"{WS}/Sales.SemanticModel/definition/model.tmdl",
        f"{WS}/Budget.Report/definition.pbir",
        f"{WS}/Budget.SemanticModel/definition/model.tmdl",
    ])
 
    assert changes.workspace == WS
    assert len(changes.items) == 4

def test_touching_only_a_report_leaves_models_empty() -> None:
    """Rule 3. Changing a visual must not queue the model for analysis"""

    changes: ChangeSet = resolve([f"{WS}/Sales.Report/definition/pages.json"])
 
    assert changes.semantic_models == []
    assert len(changes.reports) == 1

def test_paths_outside_a_workspace_are_ignored() -> None:
    """A pull request touching only the pipeline resolves to nothing
    and must not fail."""
    changes: ChangeSet = resolve([
        "README.md",
        "src/pbi_cicd/rules/scope.py",
        ".github/workflows/powerbi_ci.yaml",
    ])
 
    assert not changes.has_changes
    assert changes.workspace is None

def test_file_directly_under_a_workspace_is_ignored() -> None:
    """`.gitignore` lives here and belongs to no item. The workspace is
    still reported, since something inside it did change."""
    changes = resolve([f"{WS}/.gitignore"])
 
    assert not changes.has_changes
    assert changes.workspace == WS

def test_deep_path_with_no_item_raises() -> None:
    """Deep path with no item"""
    with pytest.raises(PipelineError) as exc:
        resolve([f"{WS}/documentation/manual.pdf"])
 
    assert "manual.pdf" in str(exc.value)

def test_deleted_files_resolve_to_items() -> None:
    """Deletions are reported, never validated. Rule 1 does not apply:
    it governs what a pull request changes, not what it removes."""
    removed: list[Item] = resolve_removed([
        f"{OTHER_WS}/Budget.Report/.platform",
        f"{OTHER_WS}/Budget.SemanticModel/.platform",
    ])
 
    assert {item.path for item in removed} == {
        f"{OTHER_WS}/Budget.Report",
        f"{OTHER_WS}/Budget.SemanticModel",
    }