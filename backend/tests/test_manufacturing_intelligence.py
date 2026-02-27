"""
Verification test for Phase A Manufacturing Geometry Intelligence Engine.

Tests:
  1. Schema import and instantiation
  2. Validation enforcement (rejects invalid data)
  3. JSON schema generation
  4. Full report assembly and round-trip validation
  5. Intelligence module imports
"""

import json
import sys
from uuid import uuid4


def test_schemas():
    """Test all Pydantic schema models."""
    from cad_worker.schemas.manufacturing_geometry_report import (
        BoundingBox, GeometrySummary, FaceNode, EdgeNode, TopologyGraph,
        FeatureSpatial, StockRecommendation, DatumCandidates,
        ManufacturabilityWarning, ManufacturabilityAnalysis,
        ComplexityScore, ManufacturingGeometryReport,
    )

    # Test 1: Basic instantiation
    print("=== Test 1: Schema instantiation ===")
    bbox = BoundingBox(length=100.0, width=50.0, height=25.0)
    print(f"  BoundingBox: {bbox.model_dump()}")

    gs = GeometrySummary(
        bounding_box=bbox, volume=125000.0, surface_area=17500.0,
        center_of_mass=(50.0, 25.0, 12.5),
    )
    print(f"  GeometrySummary volume: {gs.volume}")

    fn = FaceNode(
        id="F_001", surface_type="PLANAR", area=5000.0,
        normal=(0.0, 0.0, 1.0), center=(50.0, 25.0, 25.0),
        adjacent_faces=["F_002", "F_003"],
    )
    print(f"  FaceNode: {fn.id} type={fn.surface_type}")

    en = EdgeNode(id="E_001", length=100.0, connected_faces=["F_001", "F_002"])
    print(f"  EdgeNode: {en.id} length={en.length}")

    cs = ComplexityScore(value=0.45, level="MEDIUM")
    print(f"  ComplexityScore: {cs.value} ({cs.level})")
    print("  PASSED")

    # Test 2: Validation enforcement
    print("\n=== Test 2: Validation enforcement ===")
    try:
        ComplexityScore(value=1.5, level="LOW")
        print("  ERROR: Should have rejected value=1.5")
        return False
    except Exception as e:
        print(f"  Correctly rejected value=1.5: {type(e).__name__}")

    try:
        FaceNode(id="F_001", surface_type="INVALID", area=100.0,
                 normal=(0, 0, 1), center=(0, 0, 0))
        print("  ERROR: Should have rejected surface_type=INVALID")
        return False
    except Exception as e:
        print(f"  Correctly rejected surface_type=INVALID: {type(e).__name__}")

    try:
        StockRecommendation(type="CYLINDER", length=100, width=50, height=25)
        print("  ERROR: Should have rejected type=CYLINDER")
        return False
    except Exception as e:
        print(f"  Correctly rejected stock type=CYLINDER: {type(e).__name__}")
    print("  PASSED")

    # Test 3: JSON schema generation
    print("\n=== Test 3: JSON schema generation ===")
    schema = ManufacturingGeometryReport.model_json_schema()
    props = list(schema.get("properties", {}).keys())
    defs = list(schema.get("$defs", {}).keys())
    print(f"  Top-level properties ({len(props)}): {props}")
    print(f"  Sub-schema definitions ({len(defs)}): {defs}")
    assert len(props) == 8, f"Expected 8 properties, got {len(props)}"
    print("  PASSED")

    # Test 4: Full report assembly and round-trip
    print("\n=== Test 4: Full report assembly ===")
    report = ManufacturingGeometryReport(
        model_id=uuid4(),
        geometry_summary=gs,
        topology_graph=TopologyGraph(faces=[fn], edges=[en]),
        features=[
            FeatureSpatial(
                id="FEAT_001", type="HOLE", diameter=10.0, depth=20.0,
                position=(25.0, 25.0, 0.0), axis_direction=(0.0, 0.0, 1.0),
                parent_face_id="F_001",
                accessibility_direction=(0.0, 0.0, -1.0),
                is_through=False,
            )
        ],
        stock_recommendation=StockRecommendation(
            type="BLOCK", length=104.0, width=54.0, height=29.0,
        ),
        datum_candidates=DatumCandidates(
            primary="F_001",
            reasoning="Largest planar face with Z-aligned normal.",
        ),
        manufacturability_analysis=ManufacturabilityAnalysis(warnings=[
            ManufacturabilityWarning(
                type="THIN_WALL", severity="MEDIUM",
                reason="Wall thickness 1.5mm between F_002 and F_003",
            ),
        ]),
        complexity_score=cs,
    )

    report_json = report.model_dump(mode="json")
    serialized = json.dumps(report_json, indent=2)
    print(f"  Serialized: {len(serialized)} chars")
    print(f"  model_id type: {type(report_json['model_id']).__name__}")
    print(f"  Features: {len(report_json['features'])}")
    print(f"  Warnings: {len(report_json['manufacturability_analysis']['warnings'])}")

    # Validate round-trip
    validated = ManufacturingGeometryReport.model_validate(report_json)
    assert str(validated.model_id) == report_json["model_id"]
    print("  Round-trip validation: PASSED")

    return True


def test_intelligence_imports():
    """Test that all intelligence modules can be imported."""
    print("\n=== Test 5: Intelligence module imports ===")
    try:
        from cad_worker.intelligence.stock_recommender import recommend_stock
        from cad_worker.intelligence.datum_detector import detect_datums
        from cad_worker.intelligence.manufacturability_analyzer import analyze
        from cad_worker.intelligence.complexity_scorer import compute_complexity
        from cad_worker.intelligence_orchestrator import generate_manufacturing_geometry_report
        print("  All intelligence modules imported successfully")
        print("  PASSED")
        return True
    except ImportError as e:
        print(f"  Import failed: {e}")
        return False


def test_intelligence_without_occ():
    """Test intelligence modules that don't require OCC."""
    print("\n=== Test 6: Intelligence modules (no OCC) ===")
    from cad_worker.schemas import (
        GeometrySummary, BoundingBox, TopologyGraph, FaceNode,
        EdgeNode, FeatureSpatial, ManufacturabilityAnalysis,
    )

    # Build test data
    bbox = BoundingBox(length=100.0, width=50.0, height=25.0)
    gs = GeometrySummary(
        bounding_box=bbox, volume=125000.0, surface_area=17500.0,
        center_of_mass=(50.0, 25.0, 12.5),
    )
    topo = TopologyGraph(
        faces=[
            FaceNode(id="F_001", surface_type="PLANAR", area=5000.0,
                     normal=(0.0, 0.0, -1.0), center=(50.0, 25.0, 0.0),
                     adjacent_faces=["F_002", "F_003", "F_004", "F_005"]),
            FaceNode(id="F_002", surface_type="PLANAR", area=5000.0,
                     normal=(0.0, 0.0, 1.0), center=(50.0, 25.0, 25.0),
                     adjacent_faces=["F_001", "F_003", "F_004", "F_005"]),
            FaceNode(id="F_003", surface_type="PLANAR", area=2500.0,
                     normal=(0.0, -1.0, 0.0), center=(50.0, 0.0, 12.5),
                     adjacent_faces=["F_001", "F_002"]),
            FaceNode(id="F_004", surface_type="PLANAR", area=2500.0,
                     normal=(0.0, 1.0, 0.0), center=(50.0, 50.0, 12.5),
                     adjacent_faces=["F_001", "F_002"]),
            FaceNode(id="F_005", surface_type="PLANAR", area=1250.0,
                     normal=(-1.0, 0.0, 0.0), center=(0.0, 25.0, 12.5),
                     adjacent_faces=["F_001", "F_002"]),
            FaceNode(id="F_006", surface_type="PLANAR", area=1250.0,
                     normal=(1.0, 0.0, 0.0), center=(100.0, 25.0, 12.5),
                     adjacent_faces=["F_001", "F_002"]),
        ],
        edges=[
            EdgeNode(id="E_001", length=100.0, connected_faces=["F_001", "F_003"]),
            EdgeNode(id="E_002", length=50.0, connected_faces=["F_001", "F_005"]),
        ],
    )

    features = [
        FeatureSpatial(
            id="FEAT_001", type="HOLE", diameter=10.0, depth=20.0,
            position=(25.0, 25.0, 0.0), axis_direction=(0.0, 0.0, 1.0),
            parent_face_id="F_001",
            accessibility_direction=(0.0, 0.0, -1.0), is_through=False,
        ),
    ]

    # Test stock recommender
    from cad_worker.intelligence.stock_recommender import recommend_stock
    stock = recommend_stock(gs, topo)
    print(f"  Stock: {stock.type} ({stock.length}x{stock.width}x{stock.height})")
    # height/length = 25/100 = 0.25, which is NOT < 0.25 (strict less-than)
    # No cylindrical faces → cylindrical area ratio = 0 → not BAR
    # So this classifies as BLOCK, not PLATE
    assert stock.type == "BLOCK", f"Expected BLOCK, got {stock.type}"
    assert stock.allowance_per_face == 2.0

    # Test datum detector
    from cad_worker.intelligence.datum_detector import detect_datums
    datums = detect_datums(topo)
    print(f"  Primary datum: {datums.primary}")
    print(f"  Secondary datum: {datums.secondary}")
    print(f"  Reasoning: {datums.reasoning[:80]}...")
    assert datums.primary is not None
    # Verify scoring info is in reasoning
    assert "score=" in datums.reasoning, "Expected ranking score in reasoning"

    # Test manufacturability analyzer (now accepts datum_candidates)
    from cad_worker.intelligence.manufacturability_analyzer import analyze
    mfg = analyze(features, topo, datums)
    print(f"  Warnings: {len(mfg.warnings)}")
    for w in mfg.warnings:
        print(f"    - {w.type} ({w.severity}): {w.reason[:60]}...")

    # Test complexity scorer
    from cad_worker.intelligence.complexity_scorer import compute_complexity
    cx = compute_complexity(features, mfg, topo)
    print(f"  Complexity: {cx.value} ({cx.level})")
    assert 0.0 <= cx.value <= 1.0
    assert cx.level in ("LOW", "MEDIUM", "HIGH")

    print("  PASSED")
    return True


if __name__ == "__main__":
    passed = True
    passed = test_schemas() and passed
    passed = test_intelligence_imports() and passed
    passed = test_intelligence_without_occ() and passed

    print("\n" + "=" * 50)
    if passed:
        print("ALL TESTS PASSED")
        sys.exit(0)
    else:
        print("SOME TESTS FAILED")
        sys.exit(1)
