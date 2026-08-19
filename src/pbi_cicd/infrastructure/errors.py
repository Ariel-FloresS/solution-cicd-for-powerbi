"""Custom exceptions for the Power BI CI/CD pipeline."""


class PbiCicdError(Exception):
    """
    Base class for all exceptions raised by this project.
    """


class RuleViolation(PbiCicdError):
    """
    The pull request content breaks a validation rule.

    Raise this when the PR author can fix the problem by editing
    their changes. The message should say what to do about it.
    """

    def __init__(self, rule: str, message: str) -> None:
        self.rule = rule
        super().__init__(f"[RuleViolation: {rule}] {message}")


class PipelineError(PbiCicdError):
    """
    The pipeline could not run correctly.

    Raise this when the problem is the environment or configuration,
    not the PR content. The reader is whoever maintains the pipeline.
    """
    def __init__(self, message:str)-> None:
        super().__init__(f"[PipelineError: {message}]")