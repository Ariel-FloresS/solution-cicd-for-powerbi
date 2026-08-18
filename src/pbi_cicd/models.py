"""
Domain models shared by every rule.
"""
from dataclasses import dataclass, field
from pbi_cicd.errors import PipelineError

# Folder suffixes that mark a Fabric item, per the PBIP layout:https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-overview
ITEM_SUFFIXES: tuple[str, str] = (".Report", ".SemanticModel")

@dataclass(frozen=True)
class Item:
    """A Fabric item located in the repository.
 
    Frozen so instances can be deduplicated in a set, and because two
    items with the same path are the same item.
 
    `path` is relative to the repository root, for example
    `Sales_workspace/AdventureWorks.SemanticModel`. or `Sales_workspace/AdventureWorks.Report`
    """
 
    path: str
 
    def __post_init__(self) -> None:

        if not self.path.endswith(ITEM_SUFFIXES):

            raise PipelineError(
                f"Not a Fabric item path: {self.path!r}. "
                f"Expected a folder ending in one of {ITEM_SUFFIXES}."
            )
 
    @property
    def type(self) -> str:
        """Either `Report` or `SemanticModel`."""
        return self.path.rsplit(".", 1)[-1]
 
    @property
    def workspace(self) -> str:
        """Top-level folder, which maps to one Fabric workspace."""
        return self.path.split("/", 1)[0]
 
    @property
    def name(self) -> str:
        """Folder name without the type suffix.
 
        This is the name on disk, NOT the displayName stored in
        `.platform`. Rule 5 compares the two to catch divergence, so
        resolving this from the platform file would defeat the check.
        """
        return self.path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
 
    @property
    def is_semantic_model(self) -> bool:
        return self.type == "SemanticModel"
 
    @property
    def is_report(self) -> bool:
        return self.type == "Report"


@dataclass
class ChangeSet:
    """Scope detected for a pull request.
 
    Produced by `changed.resolve` and passed to every other rule so they
    only inspect what the pull request actually touched.
    """
 
    workspace: str | None = None
    items: list[Item] = field(default_factory=list)
 
    @property
    def has_changes(self) -> bool:
        return bool(self.items)
 
    @property
    def semantic_models(self) -> list[Item]:
        return [i for i in self.items if i.is_semantic_model]
 
    @property
    def reports(self) -> list[Item]:
        return [i for i in self.items if i.is_report]
 