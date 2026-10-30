"""The BPA command: python -m pbi_cicd.bpa

Exit codes: 0 the model reached the required level, 1 it did not,
2 the analysis cannot be trusted.
"""

from pathlib import Path
import argparse

from pbi_cicd.bpa import RULE
from pbi_cicd.bpa.analyzer import MODEL_DEFINITION, parse, run_analyzer
from pbi_cicd.bpa.render import annotate, render, render_failure
from pbi_cicd.bpa.scoring import evaluate, is_allowed, load_config, required_level
from pbi_cicd.infrastructure.errors import PipelineError, RuleViolation
from pbi_cicd.infrastructure.output import annotate_error
from pbi_cicd.infrastructure.report import write_section
from pbi_cicd.models import Item, Evaluation


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
        required: str = required_level(config, args.environment)

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
        write_section(args.report, render_failure(model, exc))
        return exc.exit_code

    evaluation: Evaluation = evaluate(config, violations, rule_errors)
    allowed: bool = is_allowed(evaluation.level, required)

    text = render(model, evaluation, violations, config, args.environment, required, allowed)
    print(text)
    write_section(args.report, text)
    annotate(model, evaluation, violations, config)

    if allowed:
        return 0

    violation: RuleViolation = RuleViolation(
        RULE, f"{model.name} reached {evaluation.level}; {args.environment} requires {required}."
    )
    annotate_error(violation)
    return violation.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
