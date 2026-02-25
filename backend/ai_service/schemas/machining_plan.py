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
    """Complete deterministic machining plan returned to the client."""

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
