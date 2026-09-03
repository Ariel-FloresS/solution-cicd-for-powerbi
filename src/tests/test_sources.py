from pbi_cicd.rules.sources import find_local_paths

def test_approved_connectors_pass() -> None:
    """Rule 6 looks for local paths, not for an allow-list of
    connectors."""
    tmdl: str = """
    partition Sales = m
        mode: import
        source =
            let
                Source = Snowflake.Databases("account.snowflakecomputing.com", "WH"),
                Files = SharePoint.Files("https://company.sharepoint.com/sites/sales"),
                Lake = AzureStorage.DataLake("https://account.dfs.core.windows.net/data"),
                Api = Web.Contents("https://api.company.com/v1/sales")
            in
                Source
    """
 
    assert find_local_paths(tmdl) == []

def test_transformations_are_not_mistaken_for_sources() -> None:
    
    tmdl: str = """
        #"Promoted" = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
        #"Trimmed" = Text.Trim([Name]),
        #"Total" = List.Sum(Values),
        #"Parsed" = Date.FromText([Period])
    """
 
    assert find_local_paths(tmdl) == []

def test_windows_drive_path_is_detected() -> None:
    
    tmdl: str = r'Source = Csv.Document(File.Contents("C:\Users\user\sales.csv"))'
 
    findings : list[tuple[str, str]] = find_local_paths(tmdl)
 
    assert len(findings) == 1
    label, line = findings[0]
    assert label == "Windows drive path"
    assert "sales.csv" in line

def test_every_pattern_fires() -> None:
    
    cases: dict[str,str] = {
        "Windows drive path": r'Excel.Workbook(File.Contents("D:/data/budget.xlsx"))',
        "local file URI": 'Web.Contents("file:///tmp/config.json")',
        "home directory path": 'Csv.Document(File.Contents("/Users/adriana/sales.csv"))',
    }
 
    for expected_label, line in cases.items():
        findings: list[tuple[str, str]] = find_local_paths(line)
        assert findings, f"{expected_label} matched nothing"
        assert findings[0][0] == expected_label

