"""The quality gate algorithm.

  1. Any violated blocker                      -> NO APROBADO
  2. A scored rule that failed to evaluate     -> NO APROBADO
  3. Otherwise each score group gets a level:
       score >= ceil(approvedPct    * max)     -> APROBADO
       score >= ceil(conditionalPct * max)     -> CONDICIONAL
       below that                              -> NO APROBADO
     and the model takes its worst group's level.

A group's max is the sum of its rules' points. Each violated rule
deducts its points once, however many objects break it. Rules missing
from gate_config.json are informational; excluded rules are ignored.
"""

from decimal import ROUND_CEILING, Decimal
from pathlib import Path
import json

from pbi_cicd.infrastructure.errors import PipelineError
from pbi_cicd.models import GroupScore,Evaluation
NOT_APPROVED: str = "NO APROBADO"
CONDITIONAL: str = "CONDICIONAL"
APPROVED: str = "APROBADO"

# Ordered worst to best: a level passes when its index reaches the required one.
LEVELS: tuple[str, ...] = (NOT_APPROVED, CONDITIONAL, APPROVED)




def load_config(path: Path) -> dict:
    """Read gate_config.json and reject the inconsistencies that would score silently wrong."""
    try:
        config: dict = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"Could not read the gate configuration {path}: {exc}") from exc

    if not config.get("scoreGroups"):
        raise PipelineError(f"{path} defines no scoreGroups.")

    rules: dict = config.get("rules", {})
    overlap: set[str] = set(rules) & set(config.get("excluded", []))
    if overlap:
        raise PipelineError(
            f"{path} lists rules as both scored and excluded: {', '.join(sorted(overlap))}."
        )

    uncovered: list[str] = sorted(
        name for name, rule in rules.items()
        if not any(_in_group(rule, group) for group in config["scoreGroups"])
    )
    if uncovered:
        raise PipelineError(
            f"{path} has rules whose category belongs to no score group, so their "
            f"points would never count: {', '.join(uncovered)}."
        )

    return config


def required_level(config: dict, environment: str) -> str:
    required: str | None = config.get("requiredLevel", {}).get(environment)
    if required is None:
        raise PipelineError(
            f'Environment "{environment}" is not defined in requiredLevel of the gate configuration.'
        )
    return required


def evaluate(
    config: dict, violations: dict[str, list[str]], rule_errors: dict[str, str]
) -> Evaluation:
    rules: dict = config["rules"]
    excluded: set[str] = set(config.get("excluded", []))

    blockers: list[str] = sorted(r for r in violations if rules.get(r, {}).get("blocker"))
    deducted: list[str] = sorted(r for r in violations if r in rules)
    informational: list[str] = sorted(
        r for r in violations if r not in rules and r not in excluded
    )
    ignored: list[str] = sorted(r for r in violations if r in excluded)

    groups: list[GroupScore] = [
        _score_group(group, rules, deducted) for group in config["scoreGroups"]
    ]

    # The model's quality cannot exceed its weakest area.
    level: str = min((g.level for g in groups), key=LEVELS.index)

    if blockers:
        level = NOT_APPROVED

    # A rule that fails to evaluate cannot vouch for the model.
    failing_errors: list[str] = sorted(r for r in rule_errors if r in rules)
    if config.get("failOnRuleError", True) and failing_errors:
        level = NOT_APPROVED

    return Evaluation(
        level=level,
        groups=groups,
        blockers=blockers,
        deducted=deducted,
        informational=informational,
        excluded=ignored,
        rule_errors=rule_errors,
        failing_errors=failing_errors,
    )


def is_allowed(level: str, required: str) -> bool:
    return LEVELS.index(level) >= LEVELS.index(required)


def _score_group(group: dict, rules: dict, deducted: list[str]) -> GroupScore:
    members: dict = {name: rule for name, rule in rules.items() if _in_group(rule, group)}

    maximum: int = sum(rule["points"] for rule in members.values())
    # Each rule deducts once, however many objects violate it.
    lost: int = sum(members[name]["points"] for name in deducted if name in members)
    score: int = maximum - lost

    approved_min: int = _ceil_share(group["approvedPct"], maximum)
    conditional_min: int = _ceil_share(group["conditionalPct"], maximum)

    level: str = (
        APPROVED if score >= approved_min
        else CONDITIONAL if score >= conditional_min
        else NOT_APPROVED
    )

    return GroupScore(group["name"], score, maximum, approved_min, conditional_min, level)


def _ceil_share(pct: float, maximum: int) -> int:
    """Round a threshold up, exactly.

    `math.ceil(0.07 * 100)` is 8, because the float product is
    7.000000000000001. Going through the decimal string gives the 7 the
    algorithm expects.
    """
    return int((Decimal(str(pct)) * maximum).to_integral_value(rounding=ROUND_CEILING))


def _in_group(rule: dict, group: dict) -> bool:
    categories: str | list[str] = group["categories"]
    return categories == "*" or rule["category"] in categories
