"""
PlanningContext — Pydantic schema for the intelligence-to-planning boundary.

This is the canonical input to the deterministic base plan generator.
Produced by the intelligence adapter, consumed by all planning modules.

No planning logic here — pure data contract.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class FeatureContext(BaseModel):
    """Single feature extracted from ManufacturingGeometryReport."""

    id: str
    type: str = Field(..., description="HOLE | POCKET | SLOT | TURN_PROFILE | etc.")
    confidence: float = Field(1.0, ge=0.0, le=1.0)
    dimensions: dict = Field(default_factory=dict)
    depth: float | None = None
    diameter: float | None = None
    axis: dict | None = Field(None, description="{'x': float, 'y': float, 'z': float}")
    accessibility_direction: str | None = Field(
        None, description="TOP | BOTTOM | FRONT | BACK | LEFT | RIGHT"
    )
    hole_subtype: str | None = None
    machining_class: str | None = None
    requires_flip: bool = False
    requires_multi_axis: bool = False
    parent_feature_id: str | None = None
    tolerance: float | None = None
    surface_finish: float | None = None
    is_through: bool = False


class ManufacturabilityFlag(BaseModel):
    """Single manufacturability warning from intelligence report."""

    code: str = Field(..., description="Warning code, e.g. THIN_WALL, DEEP_POCKET")
    severity: str = Field("WARNING", description="WARNING | CRITICAL")
    message: str = ""
    affected_feature_ids: list[str] = Field(default_factory=list)


class StockRecommendation(BaseModel):
    """Raw stock material recommendation."""

    form: str = Field("BILLET", description="BILLET | BAR | PLATE")
    dimensions: dict = Field(default_factory=dict)
    material_volume: float = 0.0
    stock_volume: float = 0.0
    material_utilization: float = 0.0


class GeometryMetadata(BaseModel):
    """Geometry summary extracted from intelligence report."""

    volume: float = 0.0
    surface_area: float = 0.0
    bounding_box: dict = Field(default_factory=dict)
    planar_faces: int = 0
    cylindrical_faces: int = 0
    conical_faces: int = 0
    spherical_faces: int = 0


class PlanningContext(BaseModel):
    """
    Complete context for plan generation.

    Produced by intelligence_adapter, consumed by:
      - base_plan_generator
      - setup_planner
      - operation_planner
      - tool_planner
      - risk_integrator
      - llm_coplanner
      - strategy_generator
    """

    model_id: str
    material: str
    machine_type: str
    features: list[FeatureContext]
    geometry: GeometryMetadata = Field(default_factory=GeometryMetadata)
    datum_primary: str | None = None
    stock: StockRecommendation = Field(default_factory=StockRecommendation)
    manufacturability_flags: list[ManufacturabilityFlag] = Field(default_factory=list)
    complexity_score: float = Field(0.0, ge=0.0, le=1.0)
    optimization_goal: str = Field(
        "BALANCED",
        description="MINIMIZE_TIME | MINIMIZE_TOOL_CHANGES | BALANCED",
    )
