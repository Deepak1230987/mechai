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
    operations: list[str] = Field(
        default_factory=list,
        description="Ordered list of operation IDs executed in this setup",
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
    approved_by: str | None = Field(
        None,
        description="User ID who approved the plan (null until approved)",
    )
    approved_at: str | None = Field(
        None,
        description="ISO timestamp of approval (null until approved)",
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
