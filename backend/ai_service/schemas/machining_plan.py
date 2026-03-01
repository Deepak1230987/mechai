"""
MachiningPlan schemas — the canonical output of the rule-based planner.

These are pure Pydantic models with no DB / ORM dependency.
The planning service builds these, the route returns them, and the DB
model stores the serialised dict.

Hierarchy:
    MachiningPlanResponse
      ├─ setups:     list[SetupSpec]        (orientation + operation refs)
      ├─ operations: list[OperationSpec]    (per-feature machining steps)
      ├─ tools:      list[ToolSpec]         (unique tools selected)
      └─ estimated_time: float              (total seconds)
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── Tool ──────────────────────────────────────────────────────────────────────

class ToolSpec(BaseModel):
    """A single cutting tool selected for the plan."""

    id: str = Field(..., description="Unique tool identifier (slug)")
    type: str = Field(
        ...,
        description="Tool category: DRILL | FLAT_END_MILL | BALL_END_MILL | SLOT_CUTTER | TURNING_INSERT",
    )
    diameter: float = Field(..., ge=0, description="Tool diameter in mm")
    max_depth: float = Field(0, ge=0, description="Maximum cutting depth in mm")
    recommended_rpm_min: int = Field(0, ge=0)
    recommended_rpm_max: int = Field(0, ge=0)


# ── Operation ─────────────────────────────────────────────────────────────────

class OperationSpec(BaseModel):
    """A single machining operation tied to a feature."""

    id: str = Field(..., description="Unique operation identifier")
    feature_id: str = Field(..., description="FK to model_features.id")
    type: str = Field(
        ...,
        description=(
            "Operation type: DRILLING | POCKET_ROUGHING | POCKET_FINISHING | "
            "SLOT_MILLING | ROUGH_TURNING | FINISH_TURNING | FACE_MILLING"
        ),
    )
    tool_id: str = Field(..., description="FK to ToolSpec.id in this plan")
    parameters: dict = Field(
        default_factory=dict,
        description="Feed, speed, stepover, depth-of-cut, etc.",
    )
    estimated_time: float = Field(0, ge=0, description="Seconds for this op")


# ── Setup ─────────────────────────────────────────────────────────────────────

class SetupSpec(BaseModel):
    """One physical workholding orientation / setup."""

    setup_id: str = Field(..., description="Unique setup identifier")
    orientation: str = Field(
        ...,
        description="Workpiece orientation label, e.g. 'TOP', 'FRONT', 'CHUCK_Z'",
    )
    datum_face_id: str | None = Field(
        None, description="Primary datum face used for this setup"
    )
    operations: list[str] = Field(
        default_factory=list,
        description="Ordered list of operation IDs executed in this setup",
    )


# ── Risk ──────────────────────────────────────────────────────────────────────

class RiskItem(BaseModel):
    """A manufacturing risk attached to one or more operations."""

    code: str = Field(..., description="Risk code, e.g. THIN_WALL, DEEP_POCKET")
    severity: str = Field("WARNING", description="WARNING | CRITICAL")
    message: str = ""
    affected_operation_ids: list[str] = Field(default_factory=list)
    mitigation: str = Field("", description="Recommended mitigation action")


# ── Strategy ──────────────────────────────────────────────────────────────────

class StrategyVariant(BaseModel):
    """One planning strategy variant (conservative / optimized / aggressive)."""

    name: str = Field(..., description="CONSERVATIVE | OPTIMIZED | AGGRESSIVE")
    description: str = ""
    estimated_time: float = Field(0, ge=0)
    setup_count: int = Field(0, ge=0)
    operation_count: int = Field(0, ge=0)
    changes_from_base: list[str] = Field(
        default_factory=list,
        description="Human-readable list of changes vs. base plan",
    )


# ── Full Plan ─────────────────────────────────────────────────────────────────

class MachiningPlanResponse(BaseModel):
    """Complete machining plan returned to the client."""

    plan_id: str | None = Field(
        None,
        description="DB row ID — set by the route layer, not stored in plan_data JSON",
    )
    model_id: str
    material: str
    machine_type: str
    setups: list[SetupSpec]
    operations: list[OperationSpec]
    tools: list[ToolSpec]
    risks: list[RiskItem] = Field(
        default_factory=list,
        description="Manufacturing risk warnings attached to operations",
    )
    strategies: list[StrategyVariant] = Field(
        default_factory=list,
        description="Available strategy variants (conservative / optimized / aggressive)",
    )
    selected_strategy: str = Field(
        "CONSERVATIVE",
        description="Currently active strategy: CONSERVATIVE | OPTIMIZED | AGGRESSIVE",
    )
    llm_justification: str | None = Field(
        None,
        description="LLM co-planner's justification for optimizations applied",
    )
    estimated_time: float = Field(
        0,
        ge=0,
        description="Total estimated machining time in seconds",
    )
    version: int = Field(
        1,
        ge=1,
        description="Plan version — incremented on re-generation for same model",
    )
    approved: bool = Field(
        False,
        description="Human approval flag — always False on creation",
    )
    approval_status: str = Field(
        "DRAFT",
        description="DRAFT | PENDING_REVIEW | APPROVED | REJECTED",
    )
    approved_by: str | None = Field(
        None,
        description="User ID who approved the plan (null until approved)",
    )
    approved_at: str | None = Field(
        None,
        description="ISO timestamp of approval (null until approved)",
    )
    generation_explanation: str | None = Field(
        None,
        description="The AI's explanation for how it generated/optimized this plan",
    )
    is_rollback: bool = Field(
        False,
        description="True if this version was created via rollback",
    )
    parent_version_id: str | None = Field(
        None,
        description="ID of the version this was rolled back from (null for non-rollback)",
    )


# ── Request ───────────────────────────────────────────────────────────────────

class PlanningRequest(BaseModel):
    """Input payload for POST /planning/generate."""

    model_id: str
    material: str = Field(
        ...,
        description="Workpiece material, e.g. 'ALUMINUM_6061', 'STEEL_1045', 'TITANIUM'",
    )
    machine_type: str = Field(
        ...,
        description="Target machine: MILLING_3AXIS | LATHE",
    )


# ── Edit / Approve / Latest ──────────────────────────────────────────────────

class PlanUpdateRequest(BaseModel):
    """Input payload for POST /planning/{plan_id}/update."""

    edited_plan: dict = Field(
        ...,
        description=(
            "Full edited plan with keys: setups, operations, tools, estimated_time. "
            "model_id / material / machine_type are inherited from the original."
        ),
    )
    edited_by: str = Field(
        ...,
        description="User ID of the person making the edit",
    )


class PlanApproveRequest(BaseModel):
    """Input payload for POST /planning/{plan_id}/approve."""

    approved_by: str = Field(
        ...,
        description="User ID of the person approving the plan",
    )


class PlanDiff(BaseModel):
    """Structured diff between two plan versions."""

    operations_added: list[str] = []
    operations_removed: list[str] = []
    operations_changed: list[str] = []
    tools_changed: list[str] = []
    order_changed: bool = False
    setups_changed: bool = False
    time_delta: float = 0.0


class PlanUpdateResponse(BaseModel):
    """Response for a plan edit — new version + diff."""

    plan: MachiningPlanResponse
    diff: PlanDiff
    feedback_id: str


class VersionSummary(BaseModel):
    """Lightweight summary of one plan version — used for the version picker."""

    plan_id: str
    version: int
    approved: bool
    approved_by: str | None = None
    created_at: str
    estimated_time: float = 0
    operation_count: int = 0
    is_rollback: bool = False
    modification_reason: str | None = None


class RollbackRequest(BaseModel):
    """Input payload for POST /planning/{model_id}/rollback."""

    target_version: int = Field(
        ...,
        ge=1,
        description="Version number to roll back to",
    )
    reason: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Reason for the rollback",
    )
