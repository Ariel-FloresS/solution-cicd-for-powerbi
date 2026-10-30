"""How a BPA verdict is shown: the report section and the PR annotations."""

from pbi_cicd.bpa import RULE
from pbi_cicd.bpa.scoring import LEVELS
from pbi_cicd.infrastructure.errors import PipelineError, RuleViolation
from pbi_cicd.infrastructure.output import annotate_error, annotate_warning
from pbi_cicd.infrastructure.report import PIPELINE_ERROR, labelled, section
from pbi_cicd.models import Item, Evaluation

SAMPLE_OBJECTS: int = 3


def render(
    model: Item,
    evaluation: Evaluation,
    violations: dict[str, list[str]],
    config: dict,
    environment: str,
    required: str,
    allowed: bool,
) -> str:
    """The model's section of the consolidated report."""
    rules: dict = config["rules"]
    lines: list[str] = [
        f"Environment: {environment} (requires {required})",
        f"Deploy: {'allowed' if allowed else 'blocked'}",
        "",
        f"{'Group':<16}{'Score':<10}{'Approved >=':<14}{'Conditional >=':<17}Level",
    ]
    lines += [
        f"{g.name:<16}{f'{g.score}/{g.maximum}':<10}{g.approved_min:<14}"
        f"{g.conditional_min:<17}{g.level}"
        for g in evaluation.groups
    ]

    override: str | None = _override_reason(evaluation)
    if override:
        lines += ["", f"Final level: {evaluation.level} - {override}"]

    if evaluation.blockers:
        lines += ["", "BLOCKERS VIOLATED"]
        for name in evaluation.blockers:
            lines += _rule_block(name, violations[name], rules[name]["points"])

    scoring: list[str] = [r for r in evaluation.deducted if r not in evaluation.blockers]
    if scoring:
        lines += ["", "RULES DEDUCTING POINTS"]
        for name in scoring:
            lines += _rule_block(name, violations[name], rules[name]["points"])

    if evaluation.rule_errors:
        lines += ["", "RULES THAT FAILED TO EVALUATE"]
        lines += [f"  {name}: {message}" for name, message in evaluation.rule_errors.items()]

    if evaluation.informational:
        lines += ["", f"INFORMATIONAL - reported, not scored ({len(evaluation.informational)})"]
        lines += [
            f"  {name:<60} {len(violations[name])} object(s)"
            for name in evaluation.informational
        ]

    if evaluation.excluded:
        lines += ["", "EXCLUDED - need a published model to evaluate"]
        lines += [f"  {name}" for name in evaluation.excluded]

    return section(f"BPA - {model.name}", evaluation.level, lines)


def render_failure(model: Item, error: PipelineError) -> str:
    """The section written when the analysis itself could not run."""
    lines: list[str] = labelled("ERROR", error) + [
        "",
        "The gate could not reach a verdict. This is not a problem with",
        "the model: whoever maintains the pipeline should look at it.",
    ]
    return section(f"BPA - {model.name}", PIPELINE_ERROR, lines)


def annotate(
    model: Item, evaluation: Evaluation, violations: dict[str, list[str]], config: dict
) -> None:
    """Surface the findings that decided the verdict on the pull request."""
    rules: dict = config["rules"]

    for name in evaluation.blockers:
        annotate_error(RuleViolation(
            RULE,
            f"{model.name} violates blocker {name} in {len(violations[name])} object(s). "
            "A blocker fails the model whatever its score.",
        ))

    for name in evaluation.deducted:
        if name not in evaluation.blockers:
            annotate_warning(
                f"[Rule: {RULE}] {model.name} violates {name} "
                f"(-{rules[name]['points']} pts) in {len(violations[name])} object(s)."
            )

    for name, message in evaluation.rule_errors.items():
        text: str = f"[Rule: {RULE}] {model.name}: rule {name} failed to evaluate: {message}"
        if name in evaluation.failing_errors:
            annotate_error(text)
        else:
            annotate_warning(text)


def _override_reason(evaluation: Evaluation) -> str | None:
    """Why the final level differs from what the score alone gave, if it does.

    Without this, a model at 44/48 reads APROBADO in the table and
    NO APROBADO in the heading, which looks like a contradiction to
    anyone who does not know the algorithm.
    """
    by_score: str = min((g.level for g in evaluation.groups), key=LEVELS.index)
    if evaluation.level == by_score:
        return None
    if evaluation.blockers:
        return "a blocker overrides the score"
    return "a scored rule failed to evaluate"


def _rule_block(name: str, objects: list[str], points: int) -> list[str]:
    block: list[str] = [f"  {name}", f"    -{points} pts, {len(objects)} object(s)"]
    block += [f"    . {obj}" for obj in objects[:SAMPLE_OBJECTS]]
    if len(objects) > SAMPLE_OBJECTS:
        block.append(f"    . and {len(objects) - SAMPLE_OBJECTS} more")
    return block
