"""Tests for rule 7: the Best Practice Analyzer gate.

They exercise `parse` and `evaluate`, both pure. The configuration is a
small inline one rather than gate_config.json, so the tests check the
algorithm and do not break when the business reweights its rules.
"""

import pytest

from pbi_cicd.infrastructure.errors import PipelineError
from pbi_cicd.bpa.analyzer import START_MARKER, parse
from pbi_cicd.bpa.scoring import APPROVED, CONDITIONAL, NOT_APPROVED, evaluate, is_allowed

CONFIG: dict = {
    "scoreGroups": [
        {"name": "Performance", "categories": ["Performance"],
         "approvedPct": 0.9, "conditionalPct": 0.7},
    ],
    "failOnRuleError": True,
    "rules": {
        "HEAVY": {"category": "Performance", "points": 30, "blocker": False},
        "MEDIUM": {"category": "Performance", "points": 20, "blocker": False},
        "LIGHT": {"category": "Performance", "points": 10, "blocker": False},
        "OTHER": {"category": "Performance", "points": 40, "blocker": False},
        "CRITICAL": {"category": "Performance", "points": 0, "blocker": True},
    },
    "excluded": ["NEEDS_VERTIPAQ"],
}


def run(*lines: str) -> dict:
    violations, errors = parse("\n".join((START_MARKER, *lines)))
    return evaluate(CONFIG, violations, errors)


def test_output_without_the_start_marker_is_an_analysis_error() -> None:
    """Tabular Editor printing only its banner was a real incident.

    An empty violation list must never be mistaken for a clean model.
    """
    with pytest.raises(PipelineError):
        parse("Tabular Editor 2.29.0\n--------------------------------")


def test_every_output_format_yields_the_rule_name() -> None:
    """With -G, without it, and the rendered form all score the same."""
    violations, errors = parse("\n".join((
        START_MARKER,
        "::error::Model Model violates rule \"HEAVY\"",
        "Warning:  Column 'T'[c] violates rule \"MEDIUM\"",
        "Table 'T' violates rule \"LIGHT\"",
        "Error on rule 'OTHER': NullReferenceException",
    )))

    assert set(violations) == {"HEAVY", "MEDIUM", "LIGHT"}
    assert errors == {"OTHER": "NullReferenceException"}


def test_a_rule_deducts_once_however_many_objects_violate_it() -> None:
    """Max is 100. Losing 10 leaves 90, exactly the approved threshold."""
    result = run(*(f"Column 'T'[c{i}] violates rule \"LIGHT\"" for i in range(500)))

    assert result.groups[0].score == 90
    assert result.level == APPROVED


def test_group_levels_follow_the_thresholds() -> None:
    """The algorithm's own example: 100 max, thresholds 90 and 70."""
    assert run('M violates rule "LIGHT"').level == APPROVED            # 90
    assert run('M violates rule "MEDIUM"').level == CONDITIONAL        # 80
    assert run('M violates rule "OTHER"').level == NOT_APPROVED        # 60


def test_a_blocker_fails_the_model_whatever_its_score() -> None:
    """The blocker is worth 0 points, so the score stays at 100/100."""
    result = run('T violates rule "CRITICAL"')

    assert result.groups[0].score == 100
    assert result.level == NOT_APPROVED


def test_a_scored_rule_that_fails_to_evaluate_fails_the_model() -> None:
    result = run("Error on rule 'HEAVY': NullReferenceException")

    assert result.level == NOT_APPROVED


def test_excluded_and_unconfigured_rules_never_deduct() -> None:
    result = run('T violates rule "NEEDS_VERTIPAQ"', 'T violates rule "NOT_IN_CONFIG"')

    assert result.groups[0].score == 100
    assert result.excluded == ["NEEDS_VERTIPAQ"]
    assert result.informational == ["NOT_IN_CONFIG"]


def test_thresholds_round_up_exactly() -> None:
    """0.07 x 100 is 7.000000000000001 in float, which math.ceil turns into 8."""
    config: dict = {
        "scoreGroups": [{"name": "G", "categories": "*",
                         "approvedPct": 0.07, "conditionalPct": 0.07}],
        "rules": {"R": {"category": "Any", "points": 100, "blocker": False}},
    }

    result = evaluate(config, {}, {})

    assert result.groups[0].approved_min == 7


def test_a_level_passes_when_it_reaches_the_requirement() -> None:
    assert is_allowed(APPROVED, CONDITIONAL)
    assert is_allowed(CONDITIONAL, CONDITIONAL)
    assert not is_allowed(CONDITIONAL, APPROVED)
    assert not is_allowed(NOT_APPROVED, CONDITIONAL)


def test_the_model_takes_the_level_of_its_weakest_group() -> None:
    """One group approved and one not approved yields not approved."""
    config: dict = {
        "scoreGroups": [
            {"name": "Modeling", "categories": ["Modeling"],
             "approvedPct": 0.9, "conditionalPct": 0.7},
            {"name": "Governance", "categories": ["Governance"],
             "approvedPct": 0.9, "conditionalPct": 0.7},
        ],
        "rules": {
            "M": {"category": "Modeling", "points": 10, "blocker": False},
            "G": {"category": "Governance", "points": 10, "blocker": False},
        },
    }

    result = evaluate(config, {"G": ["Model"]}, {})

    assert [g.level for g in result.groups] == [APPROVED, NOT_APPROVED]
    assert result.level == NOT_APPROVED

def test_the_report_explains_when_the_level_overrides_the_score() -> None:
    """A model at its approved threshold that fails only on a blocker.

    The table shows APROBADO and the heading NO APROBADO; the report
    must say why, and stay silent when there is nothing to explain.
    """
    from pbi_cicd.bpa.render import render
    from pbi_cicd.models import Item

    model: Item = Item("WS/Sales.SemanticModel")

    violations, errors = parse(f'{START_MARKER}\nT violates rule "CRITICAL"')
    blocked: str = render(model, evaluate(CONFIG, violations, errors), violations,
                          CONFIG, "prod", APPROVED, False)
    assert "Final level: NO APROBADO - a blocker overrides the score" in blocked

    violations, errors = parse(f'{START_MARKER}\nT violates rule "LIGHT"')
    clean: str = render(model, evaluate(CONFIG, violations, errors), violations,
                        CONFIG, "prod", APPROVED, True)
    assert "Final level" not in clean
