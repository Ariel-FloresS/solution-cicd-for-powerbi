"""Rule 7: semantic models must pass the Best Practice Analyzer gate.

Tabular Editor evaluates the model against bpa_rules.json. The violations
are then scored with gate_config.json: blockers fail outright, every other
configured rule deducts its points once per score group, and the worst
group sets the model's level. That level must reach what the environment
requires.

Exit codes: 0 gate passed, 1 gate failed, 2 the analysis cannot be trusted.
"""

from pbi_cicd.infrastructure.errors import PipelineError, RuleViolation
from pbi_cicd.infrastructure.output import annotate_error, annotate_warning
from pbi_cicd.models import Item,GroupScore,Evaluation
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
import argparse
import json
import re
import subprocess


RULE: str = "7"

NOT_APPROVED: str = "NO APROBADO"
CONDITIONAL: str = "CONDICIONAL"
APPROVED: str = "APROBADO"

# Ordered worst to best: a level passes when its index reaches the required one.
LEVELS: tuple[str, ...] = (NOT_APPROVED, CONDITIONAL, APPROVED)

GATE_PASSED: int = 0
GATE_FAILED: int = 1
ANALYSIS_ERROR: int = 2

MODEL_DEFINITION: Path = Path("definition") / "model.tmdl"


START_MARKER: str = "Running Best Practice Analyzer..."

VIOLATION_RE: re.Pattern[str] = re.compile(
    r'^(?:(?:::(?:error|warning)::|Error:|Warning:)\s*)?'
    r'(?P<object>.+?) violates rule "(?P<rule>[^"]+)"\s*$'
)
RULE_ERROR_RE: re.Pattern[str] = re.compile(
    r"^(?:::error::\s*)?Error on rule '(?P<rule>[^']+)': (?P<message>.*)$"
)

TIMEOUT_SECONDS: int = 600
SAMPLE_OBJECTS: int = 3


def run_analyzer(exe: Path, definition: Path, rules_file: Path, output: Path) -> str:
    """Run Tabular Editor and return everything it printed.
 
    TabularEditor.exe is a GUI-subsystem binary: called directly it returns
    at once and keeps writing in the background, so the runner kills it
    mid-analysis. `start /WAIT` is what Tabular Editor's documentation
    prescribes to block until it finishes.
    """
    command: str = (
        f'start "" /B /WAIT "{exe}" "{definition}" -A "{rules_file}" > "{output}" 2>&1'
    )
 
    try:
        subprocess.run(command, shell=True, timeout=TIMEOUT_SECONDS, check=False)
    except subprocess.TimeoutExpired as exc:
        raise PipelineError(
            f"Tabular Editor did not finish within {TIMEOUT_SECONDS} seconds."
        ) from exc
 
    try:
        return output.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        raise PipelineError(f"Could not read the analyzer output at {output}: {exc}") from exc
 
 
def parse(text: str) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Return the objects violating each rule, and the rules that failed to evaluate."""
    if START_MARKER not in text:
        raise PipelineError(
            f'The analyzer output lacks "{START_MARKER}": Tabular Editor never '
            "evaluated the model, so its silence cannot be read as a pass."
        )
 
    violations: dict[str, list[str]] = {}
    rule_errors: dict[str, str] = {}
 
    line: str
    for line in text.splitlines():
        line = line.strip()
 
        if match := VIOLATION_RE.match(line):
            violations.setdefault(match["rule"], []).append(match["object"])
        elif match := RULE_ERROR_RE.match(line):
            rule_errors[match["rule"]] = match["message"]
 
    return violations, rule_errors
 
 
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
 
 
def evaluate(
    config: dict, violations: dict[str, list[str]], rule_errors: dict[str, str]
) -> Evaluation:
    """Apply the gate algorithm exactly as the business defined it."""
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
    lines: list[str] = _header(f"BPA - {model.name}", evaluation.level)
    lines += [
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
 
    if evaluation.blockers:
        lines += ["", "BLOCKERS VIOLATED"]
        for name in evaluation.blockers:
            detail: str = f"-{rules[name]['points']} pts, {len(violations[name])} object(s)"
            lines += _rule_block(name, violations[name], detail)
 
    scoring: list[str] = [r for r in evaluation.deducted if r not in evaluation.blockers]
    if scoring:
        lines += ["", "RULES DEDUCTING POINTS"]
        for name in scoring:
            lines += _rule_block(
                name, violations[name], f"-{rules[name]['points']} pts, {len(violations[name])} object(s)"
            )
 
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
 
    return "\n".join(lines) + "\n"
 
 
def render_failure(model: Item, error: PipelineError) -> str:
    """The section written when the analysis itself could not run."""
    lines: list[str] = _header(f"BPA - {model.name}", "ANALYSIS ERROR")
    lines += [str(error), "", "The gate could not reach a verdict. This is not a"]
    lines += ["problem with the model: whoever maintains the pipeline should look at it."]
    return "\n".join(lines) + "\n"
 
 
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
 
 
def _rule_block(name: str, objects: list[str], detail: str) -> list[str]:
    block: list[str] = [f"  {name}", f"    {detail}"]
    block += [f"    . {obj}" for obj in objects[:SAMPLE_OBJECTS]]
    if len(objects) > SAMPLE_OBJECTS:
        block.append(f"    . and {len(objects) - SAMPLE_OBJECTS} more")
    return block
 
 
def _header(title: str, status: str) -> list[str]:
    rule: str = "=" * 72
    return [rule, f"{title:<52}{status:>20}", rule]
 
 
def _required_level(config: dict, environment: str) -> str:
    required: str | None = config.get("requiredLevel", {}).get(environment)
    if required is None:
        raise PipelineError(
            f'Environment "{environment}" is not defined in requiredLevel of the gate configuration.'
        )
    return required
 
 
def _write_report(path: Path | None, text: str) -> None:
    if path is None:
        return
    path.write_text(text, encoding="utf-8")
 
 
def main(argv: list[str] | None = None) -> int:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Rule 7: semantic models must pass the Best Practice Analyzer gate."
    )
    parser.add_argument("--model", required=True, help="Path of the .SemanticModel folder, from the scope job.")
    parser.add_argument("--environment", required=True, help="Key into requiredLevel of the gate configuration.")
    parser.add_argument("--tabular-editor", type=Path, required=True, help="Path to TabularEditor.exe.")
    parser.add_argument("--rules", type=Path, default=Path("src/tabula/bpa_rules.json"))
    parser.add_argument("--config", type=Path, default=Path("src/tabula/gate_config.json"))
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--analyzer-output", type=Path, default=Path("bpa-output.txt"))
    parser.add_argument("--report", type=Path, help="Where to write this model's report section.")
    args: argparse.Namespace = parser.parse_args(argv)
 
    model: Item = Item(path=args.model)
 
    try:
        config: dict = load_config(args.config)
        required: str = _required_level(config, args.environment)
 
        definition: Path = (args.repo_root / model.path / MODEL_DEFINITION).resolve()
        if not definition.is_file():
            raise PipelineError(f"{model.path} has no {MODEL_DEFINITION.as_posix()}.")
 
        text: str = run_analyzer(
            args.tabular_editor.resolve(), definition,
            args.rules.resolve(), args.analyzer_output.resolve(),
        )
        violations, rule_errors = parse(text)
    except PipelineError as exc:
        annotate_error(exc)
        _write_report(args.report, render_failure(model, exc))
        return ANALYSIS_ERROR
 
    evaluation: Evaluation = evaluate(config, violations, rule_errors)
    allowed: bool = is_allowed(evaluation.level, required)
 
    section: str = render(model, evaluation, violations, config, args.environment, required, allowed)
    print(section)
    _write_report(args.report, section)
    annotate(model, evaluation, violations, config)
 
    if allowed:
        return GATE_PASSED
 
    annotate_error(RuleViolation(
        RULE,
        f"{model.name} reached {evaluation.level}; {args.environment} requires {required}.",
    ))
    return GATE_FAILED
 
 
if __name__ == "__main__":
    raise SystemExit(main())