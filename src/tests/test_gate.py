"""Tests for the pull request gate.

`failed_jobs` decides the merge; `consolidate` builds the report a
non-technical reader receives. Both are pure.
"""

from datetime import datetime, timezone

from pbi_cicd.gate import consolidate, failed_jobs

NOW: datetime = datetime(2026, 10, 24, 18, 0, tzinfo=timezone.utc)


def test_skipped_jobs_do_not_block_the_merge() -> None:
    """With no semantic models changed the BPA is skipped, and that is a pass.

    A skipped job counting as a failure would block every report-only change.
    """
    needs: dict = {
        "scope": {"result": "success"},
        "validate_artefacts": {"result": "success"},
        "bpa-rules": {"result": "skipped"},
    }

    assert failed_jobs(needs) == []


def test_failed_and_cancelled_jobs_block_the_merge() -> None:
    needs: dict = {
        "scope": {"result": "success"},
        "validate_artefacts": {"result": "failure"},
        "bpa-rules": {"result": "cancelled"},
    }

    assert failed_jobs(needs) == ["bpa-rules", "validate_artefacts"]


def test_the_report_follows_the_order_the_jobs_run() -> None:
    """Artifacts download in whatever order; the reader expects scope first."""
    needs: dict = {
        "scope": {"result": "success", "outputs": {"workspace": "WS1"}},
        "validate_artefacts": {"result": "failure"},
        "bpa-rules": {"result": "failure"},
    }
    sections: dict[str, str] = {
        "report-bpa-1": "BPA SECOND",
        "report-validate": "ERROR    [RuleViolation: 4] bad name",
        "report-bpa-0": "BPA FIRST",
        "report-scope": "Workspace: WS1",
    }

    report: str = consolidate(needs, sections, "42", "123", NOW)

    order: list[int] = [
        report.index(marker)
        for marker in ("Workspace: WS1", "bad name", "BPA FIRST", "BPA SECOND")
    ]
    assert order == sorted(order)
    assert "PR #42" in report


def test_a_failed_job_without_a_section_is_still_explained() -> None:
    """A job that dies before writing must not leave a silent hole."""
    needs: dict = {
        "scope": {"result": "success", "outputs": {"workspace": "WS1"}},
        "validate_artefacts": {"result": "failure"},
        "bpa-rules": {"result": "skipped"},
    }

    report: str = consolidate(needs, {"report-scope": "Workspace: WS1"}, "42", "123", NOW)

    assert "VALIDATE_ARTEFACTS" in report
    assert "without leaving a report" in report
