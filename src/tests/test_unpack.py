

from pbi_cicd.infrastructure.errors import PipelineError
from pbi_cicd.rules.name import ALLOWED_NAME, suggest
from pbi_cicd.unpack import extract, locate, plan
from pathlib import Path
import io
import pytest
import zipfile


def test_the_blob_path_names_the_workspace_and_the_dashboard() -> None:
    """The path is the contract with Data Factory, so its shape is enforced."""
    assert locate("intake/WORKSPACE_1/Ventas.zip", "intake") == ("WORKSPACE_1", "Ventas")

    for blob in (
        "intake/Ventas.zip",                  # no workspace
        "intake/WORKSPACE_1/2026/Ventas.zip", # nested
        "other/WORKSPACE_1/Ventas.zip",       # outside the intake folder
        "intake/WORKSPACE_1/Ventas.pbix",     # not a zip
    ):
        with pytest.raises(PipelineError):
            locate(blob, "intake")


def test_noise_is_dropped_and_a_wrapper_folder_is_tolerated() -> None:
    """A real export zipped from its parent folder, with what macOS, Windows
    and Desktop leave behind. Windows ignores case, so neither does the filter."""
    names: list[str] = [
        "Ventas/Ventas.pbip",
        "Ventas/Ventas.Report/definition.pbir",
        "Ventas/Ventas.Report/.pbi/localSettings.json",
        "Ventas/Ventas.SemanticModel/definition/model.tmdl",
        "Ventas/Ventas.SemanticModel/.pbi/cache.abf",
        "Ventas/Ventas.SemanticModel/Desktop.ini",
        "Ventas/Ventas.Report/StaticResources/Thumbs.db",
        "__MACOSX/Ventas/._Ventas.pbip",
        "Ventas/.DS_Store",
    ]

    delivery = plan("WORKSPACE_1", "Ventas", names)

    assert sorted(delivery.files.values()) == [
        "Ventas.Report/definition.pbir",
        "Ventas.SemanticModel/definition/model.tmdl",
    ]


def test_a_zip_without_both_matching_folders_is_rejected() -> None:
    """The folders must match the zip's name: that name becomes the PR title."""
    with pytest.raises(PipelineError):
        plan("WORKSPACE_1", "Ventas", ["Ventas.Report/definition.pbir"])
    with pytest.raises(PipelineError):
        plan("WORKSPACE_1", "Ventas", ["Compras.Report/x", "Compras.SemanticModel/x"])


def test_a_path_escaping_the_workspace_is_rejected() -> None:
    with pytest.raises(PipelineError):
        plan("WORKSPACE_1", "Ventas", ["Ventas.Report/../../.github/workflows/evil.yaml"])


def test_a_new_version_replaces_the_old_one(tmp_path: Path) -> None:
    """A page deleted in the new version must not survive from the old one."""
    old_page: Path = tmp_path / "WORKSPACE_1" / "Ventas.Report" / "old_page.json"
    old_page.parent.mkdir(parents=True)
    old_page.write_text("old")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("Ventas.Report/definition.pbir", "{}")
        archive.writestr("Ventas.SemanticModel/definition/model.tmdl", "model")

    with zipfile.ZipFile(buffer) as archive:
        extract(archive, plan("WORKSPACE_1", "Ventas", archive.namelist()), tmp_path)

    assert not old_page.exists()
    assert (tmp_path / "WORKSPACE_1" / "Ventas.Report" / "definition.pbir").exists()


def test_every_suggestion_is_a_valid_name() -> None:
    """The intake names its branch with suggest(), and git rejects spaces.

    The fallback for a name with nothing to keep once had a space in it.
    """
    for name in ("(((", "Visualización_Ventas (1)", "Análisis Ñoño", "   "):
        assert ALLOWED_NAME.match(suggest(name)), name