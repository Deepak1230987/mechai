"""
LLM Diff Schema — structured output that the LLM co-planner must produce.

The LLM never outputs a full plan. It outputs a *diff* against the
deterministic base plan. This constrains the LLM's action space and
makes validation tractable.

Rules enforced:
  • LLM cannot create new features
  • LLM cannot remove safety operations
  • LLM must reference existing feature IDs
  • LLM must output valid JSON matching this schema
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class OperationReorder(BaseModel):
    """Request to move an operation to a different position."""

    operation_id: str = Field(..., description="Existing operation ID to move")
    new_position: int = Field(
        ..., ge=0,
        description="0-based index in the final operation sequence"
    )
    reason: str = ""


class ToolChange(BaseModel):
    """Request to swap a tool for an operation."""

    operation_id: str = Field(..., description="Operation whose tool should change")
    current_tool_id: str = Field(..., description="Tool ID being replaced")
    proposed_tool_id: str = Field(..., description="New tool ID (must be valid)")
    proposed_tool_type: str = ""
    proposed_tool_diameter: float = Field(0, ge=0)
    reason: str = ""


class ParameterChange(BaseModel):
    """Request to modify cutting parameters for an operation."""

    operation_id: str
    parameter_name: str = Field(
        ..., description="e.g. stepover_pct, doc_pct, depth"
    )
    old_value: float | str | None = None
    new_value: float | str | None = None
    reason: str = ""


class SetupModification(BaseModel):
    """Request to merge, split, or reorder setups."""

    action: str = Field(
        ..., description="MERGE | SPLIT | REORDER"
    )
    setup_ids: list[str] = Field(
        default_factory=list,
        description="Setup IDs affected by this modification",
    )
    proposed_orientation: str | None = Field(
        None, description="New orientation for merged/split setup"
    )
    operations_to_move: list[str] = Field(
        default_factory=list,
        description="Operation IDs to reassign between setups",
    )
    reason: str = ""


class OperationAddition(BaseModel):
    """LLM proposes adding a new operation for an existing feature."""

    feature_id: str = Field(
        ..., description="MUST reference an existing feature ID"
    )
    op_type: str = Field(
        ..., description="Operation type: SPOT_DRILL | REAMING | CHAMFER | etc."
    )
    insert_after: str | None = Field(
        None, description="Operation ID after which to insert"
    )
    tool_type: str = ""
    tool_diameter: float = Field(0, ge=0)
    parameters: dict = Field(default_factory=dict)
    reason: str = ""


class LLMDiff(BaseModel):
    """
    Structured diff produced by the LLM co-planner.

    This is the ONLY output format the LLM may produce.
    The plan_merger applies this diff to the deterministic base plan.
    The plan_validator checks every change before application.
    """

    operation_reorders: list[OperationReorder] = Field(default_factory=list)
    tool_changes: list[ToolChange] = Field(default_factory=list)
    parameter_changes: list[ParameterChange] = Field(default_factory=list)
    setup_modifications: list[SetupModification] = Field(default_factory=list)
    operation_additions: list[OperationAddition] = Field(default_factory=list)
    justification: str = Field(
        "", description="Overall reasoning for the proposed changes"
    )
    estimated_time_change: float = Field(
        0.0, description="Estimated time delta in seconds (negative = faster)"
    )
    confidence: float = Field(
        0.0, ge=0.0, le=1.0,
        description="LLM's self-assessed confidence in the improvement"
    )

    @property
    def is_empty(self) -> bool:
        """True if the LLM proposed no changes."""
        return (
            not self.operation_reorders
            and not self.tool_changes
            and not self.parameter_changes
            and not self.setup_modifications
            and not self.operation_additions
        )

    @property
    def change_count(self) -> int:
        return (
            len(self.operation_reorders)
            + len(self.tool_changes)
            + len(self.parameter_changes)
            + len(self.setup_modifications)
            + len(self.operation_additions)
        )
