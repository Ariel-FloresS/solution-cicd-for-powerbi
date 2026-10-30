

from pathlib import Path
import json

from pbi_cicd.validate import main

WS: str = "WORKSPACE_1"


def item(root: Path, folder: str, display_name: str, tmdl: str = "") -> str:
    """Create an item folder with its .platform and, for models, a definition."""
    path: Path = root / WS / folder
    path.mkdir(parents=True)
    (path / ".platform").write_text(json.dumps({"metadata": {"displayName": display_name}}))
    if folder.endswith(".SemanticModel"):
        (path / "definition").mkdir()
        (path / "definition" / "model.tmdl").write_text(tmdl)
    return f"{WS}/{folder}"


def run(root: Path, models: list[str], reports: list[str]) -> tuple[int, str]:
    report: Path = root / "report.txt"
    code: int = main([
        "--workspace", WS,
        "--models", json.dumps(models),
        "--reports", json.dumps(reports),
        "--repo-root", str(root),
        "--report", str(report),
    ])
    return code, report.read_text()


def test_a_clean_change_passes(tmp_path: Path) -> None:
    model: str = item(tmp_path, "Sales.SemanticModel", "Sales")
    report: str = item(tmp_path, "Sales.Report", "Sales")

    code, text = run(tmp_path, [model], [report])

    assert code == 0
    assert "PASSED" in text


def test_every_rule_runs_and_reports_even_when_another_fails(tmp_path: Path) -> None:
    """One push must surface all three problems, not one per push."""
    bad_name: str = item(tmp_path, "Sales (1).Report", "Sales")
    item(tmp_path, "Budget.Report", "Sales")
    local: str = item(tmp_path, "Ledger.SemanticModel", "Ledger",
                      tmdl='Source = Csv.Document(File.Contents("C:\\data\\x.csv"))')

    code, text = run(tmp_path, [local], [bad_name])

    assert code == 1
    assert "[RuleViolation: 4]" in text
    assert "[RuleViolation: 5]" in text
    assert "[RuleViolation: 6]" in text


def test_a_rule_that_cannot_run_is_a_pipeline_error(tmp_path: Path) -> None:
    """A broken .platform is not the author's fault, so the exit code says 2.

    The other rules still run: their findings are worth showing anyway.
    """
    model: str = item(tmp_path, "Sales.SemanticModel", "Sales")
    (tmp_path / model / ".platform").write_text("not json")

    code, text = run(tmp_path, [model], [])

    assert code == 2
    assert "PIPELINE ERROR" in text
    assert "Rule 4: passed" in text
