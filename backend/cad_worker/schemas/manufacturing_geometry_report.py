"""
Manufacturing Geometry Report — strict Pydantic v2 schema definitions.

WHY STRICT TYPING PREVENTS DOWNSTREAM AI INSTABILITY
=====================================================
This module defines the canonical data contract between the deterministic
geometry intelligence layer (Phase A) and all downstream consumers:
  • AI Process Brain (Phase B) — relies on exact field names/types for reasoning
  • Conversational Copilot (Phase C) — serialises these models into LLM context
  • Visual Manufacturing UI (Phase D) — binds 3D viewer to topology face IDs
  • RFQ Engine — uses complexity score and stock recommendation for quoting

If any field is loosely typed (e.g., `dict` instead of `BoundingBox`), then:
  1. LLM hallucination risk increases — the AI cannot validate its own output
  2. Frontend rendering fails silently — missing keys cause undefined behavior
  3. Database queries become unreliable — JSONB path queries assume structure
  4. Serialization round-trips corrupt data — `Optional[Any]` loses type info

By using Pydantic v2 with `Literal` constraints, `tuple` vectors, and explicit
`Optional` markers, we guarantee that:
  • Every field is validated at write time (Pydantic raises, not the DB)
  • JSON schema is auto-generated for API docs and frontend codegen
  • Partial reports (from orchestrator failure recovery) are still valid
  • AI modules receive guaranteed-shape input — no "sometimes a list,
    sometimes a dict" ambiguity

ENGINEERING RULES APPLIED
=========================
  • All 3D vectors are tuple[float, float, float] — not dict, not list
  • All enums use Literal[] — not str, not Enum class (JSON-friendly)
  • All measurements are float — never int (avoids integer division bugs)
  • Optional fields have explicit defaults — never None-surprise
  • UUID is validated — prevents injection of malformed IDs
  • model_config strict mode OFF (Pydantic v2 default) — allows OCC float coercion
"""

from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── Geometry Summary ──────────────────────────────────────────────────────────

class BoundingBox(BaseModel):
    """
    Axis-aligned bounding box dimensions.

    Represents the minimum enclosing rectangular prism aligned
    to the world coordinate axes (X, Y, Z).

    Units: model units (typically mm in ISO STEP files).
    """
    length: float = Field(..., description="Extent along the longest axis (X)")
    width: float = Field(..., description="Extent along the second axis (Y)")
    height: float = Field(..., description="Extent along the shortest axis (Z)")


class GeometrySummary(BaseModel):
    """
    Global geometric properties of the solid model.

    These are the first metrics any process planner examines:
      • Bounding box → raw stock size estimation
      • Volume → material cost estimation
      • Surface area → finish time estimation
      • Center of mass → workholding stability analysis
    """
    bounding_box: BoundingBox
    volume: float = Field(..., ge=0.0, description="Solid volume in model_units³")
    surface_area: float = Field(..., ge=0.0, description="Total surface area in model_units²")
    center_of_mass: tuple[float, float, float] = Field(
        ..., description="Center of mass (x, y, z) in model coordinates"
    )


# ── Topology Graph ────────────────────────────────────────────────────────────

class FaceNode(BaseModel):
    """
    A single topological face in the BRep model.

    Each face is a bounded region of an analytic or freeform surface.
    The surface_type classification drives downstream decisions:
      • PLANAR faces → datum candidates, pocket floors
      • CYLINDRICAL faces → hole detection, turning features
      • CONICAL / SPHERICAL → complex feature classification
      • OTHER → freeform surfaces requiring 5-axis or EDM

    The normal vector is evaluated at the face centroid and normalized
    to unit length. Adjacent face IDs enable the topology walk required
    for setup planning (which faces are reachable from a single setup).
    """
    id: str = Field(..., description="Unique face identifier (e.g., 'F_001')")
    surface_type: Literal["PLANAR", "CYLINDRICAL", "CONICAL", "SPHERICAL", "OTHER"] = Field(
        ..., description="Analytic surface classification"
    )
    area: float = Field(..., ge=0.0, description="Face area in model_units²")
    normal: tuple[float, float, float] = Field(
        ..., description="Outward unit normal at face centroid"
    )
    center: tuple[float, float, float] = Field(
        ..., description="Face centroid (x, y, z)"
    )
    adjacent_faces: list[str] = Field(
        default_factory=list,
        description="IDs of faces sharing an edge with this face",
    )


class EdgeNode(BaseModel):
    """
    A single topological edge in the BRep model.

    Edges connect faces and define the feature boundaries.
    Edge length is computed via parametric curve integration
    (GCPnts_AbscissaPoint), not by endpoint distance — this
    handles curved edges correctly.
    """
    id: str = Field(..., description="Unique edge identifier (e.g., 'E_001')")
    length: float = Field(..., ge=0.0, description="Arc length of the edge")
    connected_faces: list[str] = Field(
        default_factory=list,
        description="IDs of faces on either side of this edge",
    )


class TopologyGraph(BaseModel):
    """
    Complete face-edge adjacency graph of the BRep model.

    This graph is the foundation for:
      • Setup planning — grouping accessible faces per orientation
      • Feature detection — identifying pockets, slots, bosses by adjacency
      • Datum selection — finding the largest, most stable planar face
      • 3D UI feature highlighting — mapping face IDs to rendered geometry
    """
    faces: list[FaceNode] = Field(default_factory=list)
    edges: list[EdgeNode] = Field(default_factory=list)


# ── Spatial Feature Mapping ───────────────────────────────────────────────────

class FeatureSpatial(BaseModel):
    """
    A detected machining feature with full spatial metadata.

    Every feature is anchored to the topology graph via `parent_face_id`.
    The `accessibility_direction` is the tool approach vector — opposite
    of the parent face normal — which determines whether the feature
    is reachable from a given setup orientation.

    `is_through` indicates whether the feature penetrates the full
    stock depth (e.g., through-hole vs. blind hole). This affects
    tool selection (through-drill vs. end mill) and fixturing.
    """
    id: str = Field(..., description="Unique feature identifier (e.g., 'FEAT_001')")
    type: str = Field(..., description="Feature type: HOLE, POCKET, SLOT, TURN_PROFILE")
    diameter: Optional[float] = Field(None, ge=0.0, description="Diameter (holes, cylindrical features)")
    depth: Optional[float] = Field(None, ge=0.0, description="Feature depth along access direction")
    width: Optional[float] = Field(None, ge=0.0, description="Feature width (slots, pockets)")
    length: Optional[float] = Field(None, ge=0.0, description="Feature length (slots)")
    position: tuple[float, float, float] = Field(
        ..., description="Feature centroid in global coordinates"
    )
    axis_direction: tuple[float, float, float] = Field(
        ..., description="Feature axis (cylinder axis, slot direction, etc.)"
    )
    parent_face_id: str = Field(
        ..., description="ID of the topology face this feature belongs to"
    )
    accessibility_direction: tuple[float, float, float] = Field(
        ..., description="Tool approach direction (opposite of parent face normal)"
    )
    is_through: bool = Field(
        False, description="True if feature penetrates entire stock depth"
    )


# ── Stock Recommendation ──────────────────────────────────────────────────────

class StockRecommendation(BaseModel):
    """
    Recommended raw stock geometry for machining.

    Stock type classification:
      • PLATE — flat parts where height << length/width
      • BAR   — cylindrical/rotational parts (lathe-dominant)
      • BLOCK — general prismatic parts (3-axis milling)

    Allowance per face is the extra material beyond the finished
    bounding box, required for workholding and initial facing cuts.
    Standard default: 2mm per face.
    """
    type: Literal["PLATE", "BAR", "BLOCK"] = Field(
        ..., description="Stock geometry type"
    )
    length: float = Field(..., gt=0.0, description="Stock length in model units")
    width: float = Field(..., gt=0.0, description="Stock width in model units")
    height: float = Field(..., gt=0.0, description="Stock height in model units")
    allowance_per_face: float = Field(
        2.0, ge=0.0, description="Extra material per face (mm)"
    )


# ── Datum Candidates ──────────────────────────────────────────────────────────

class DatumCandidates(BaseModel):
    """
    Recommended datum faces for workholding and measurement reference.

    The 3-2-1 locating principle requires:
      • Primary datum   — 3 contact points (largest stable planar face)
      • Secondary datum — 2 contact points (perpendicular to primary)
      • Tertiary datum  — 1 contact point (perpendicular to both)

    Reasoning explains why each face was selected, enabling
    the AI Process Brain to validate or override the choice.
    """
    primary: str = Field(..., description="Face ID of the primary datum")
    secondary: Optional[str] = Field(None, description="Face ID of the secondary datum")
    tertiary: Optional[str] = Field(None, description="Face ID of the tertiary datum")
    reasoning: str = Field(
        ..., description="Human-readable explanation of datum selection logic"
    )


# ── Manufacturability Analysis ────────────────────────────────────────────────

class ManufacturabilityWarning(BaseModel):
    """
    A single manufacturability concern detected in the geometry.

    Severity levels:
      • LOW    — informational, no process change needed
      • MEDIUM — may require special tooling or extra setup
      • HIGH   — may be unmachminable with standard 3-axis, needs review
    """
    type: str = Field(..., description="Warning category (THIN_WALL, DEEP_SLOT, etc.)")
    feature_id: Optional[str] = Field(None, description="Related feature ID, if applicable")
    severity: Literal["LOW", "MEDIUM", "HIGH"] = Field(
        ..., description="Impact severity"
    )
    reason: str = Field(..., description="Human-readable explanation")


class ManufacturabilityAnalysis(BaseModel):
    """
    Aggregated manufacturability assessment.

    An empty warnings list means the part is fully machinable
    with standard 3-axis equipment and tooling.
    """
    warnings: list[ManufacturabilityWarning] = Field(default_factory=list)


# ── Complexity Score ──────────────────────────────────────────────────────────

class ComplexityScore(BaseModel):
    """
    Normalized machining complexity assessment.

    Value range: 0.0 (trivial) to 1.0 (extremely complex).

    Classification thresholds:
      • < 0.3  → LOW    — simple prismatic, few features
      • < 0.7  → MEDIUM — moderate features, 2-3 setups
      • ≥ 0.7  → HIGH   — complex geometry, many setups, tight tolerances

    This score directly influences RFQ pricing tiers and
    lead time estimation in downstream modules.
    """
    value: float = Field(..., ge=0.0, le=1.0, description="Normalized complexity 0.0–1.0")
    level: Literal["LOW", "MEDIUM", "HIGH"] = Field(
        ..., description="Human-readable complexity tier"
    )


# ── Top-Level Report ──────────────────────────────────────────────────────────

class ManufacturingGeometryReport(BaseModel):
    """
    Complete Manufacturing Geometry Intelligence report.

    This is the single output object stored as PostgreSQL JSONB
    on the ModelGeometry record. It encapsulates ALL deterministic
    intelligence extracted from the CAD model geometry.

    Every downstream consumer (AI Brain, Copilot, UI, RFQ) reads
    from this report — it is the single source of truth for
    geometric intelligence.

    The report is assembled by the Intelligence Orchestrator, which
    wraps each engine in try/except. If a sub-engine fails, its
    section is populated with safe defaults (empty lists, zero scores),
    ensuring the report is always valid Pydantic and always storable.
    """
    model_id: UUID = Field(..., description="UUID of the CAD model this report belongs to")
    geometry_summary: GeometrySummary
    topology_graph: TopologyGraph
    features: list[FeatureSpatial] = Field(default_factory=list)
    stock_recommendation: StockRecommendation
    datum_candidates: DatumCandidates
    manufacturability_analysis: ManufacturabilityAnalysis
    complexity_score: ComplexityScore
