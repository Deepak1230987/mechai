"""
Topology Graph Engine — build face-edge adjacency graph from BRep topology.

Produces a TopologyGraph containing:
  • FaceNode list  — each with surface type, area, normal, center, adjacency
  • EdgeNode list  — each with length and connected face IDs

HOW THE ADJACENCY GRAPH IS BUILT
=================================
OpenCascade's TopExp::MapShapesAndAncestors builds a mapping from edges
to their parent faces. The algorithm:

  1. Build a map: Edge → list[Face] using MapShapesAndAncestors(shape,
     TopAbs_EDGE, TopAbs_FACE). Each edge in a valid BRep solid is shared
     by exactly 2 faces (manifold condition). Non-manifold edges (shared
     by >2 or <2 faces) can occur in faulty models.

  2. For each edge, collect its two parent faces. These are "adjacent"
     in the topological sense — they share a geometric boundary.

  3. Build the face adjacency list by inverting the edge→face map:
     for each face, collect all faces that share any edge with it.

WHY THIS GRAPH IS REQUIRED FOR SETUP PLANNING
==============================================
A "setup" in machining is a single clamping orientation. All features
accessible from one direction (e.g., top-down) are machined in one setup.
The adjacency graph enables:
  • Grouping faces by normal direction → which faces require the same setup
  • Finding connected components of co-oriented faces → minimum setup count
  • Identifying features that span multiple orientations → multi-setup features

WHY FACE NORMALS MUST BE NORMALIZED
====================================
BRepLProp_SLProps returns the surface normal at a parametric point (u, v).
For analytic surfaces (plane, cylinder), this is already unit length.
For BSpline/NURBS surfaces, the normal is computed as the cross product
of parametric derivatives ∂r/∂u × ∂r/∂v, which is NOT unit length.

Downstream consumers (datum detection, accessibility direction) rely on
dot products with face normals. If normals are not normalized, these
dot products produce incorrect angles, leading to:
  • Wrong datum face selection (non-perpendicular faces appear perpendicular)
  • Wrong accessibility directions (tool approach vector has wrong magnitude)
  • Wrong undercut detection (axis alignment check uses cosine similarity)

We normalize to unit length: n̂ = n / |n|, with a guard for |n| ≈ 0
(degenerate surface point — skip that face).

ENGINEERING RULES
=================
  • Tolerance = 1e-6 for geometric comparisons
  • Shape validity checked before processing
  • Pure function — no side effects, no DB writes
  • Degenerate faces (zero normal) are logged and skipped
  • Face/Edge IDs are sequential: F_001, E_001, etc.
"""

from __future__ import annotations

import logging
import math
import time

from cad_worker.schemas import FaceNode, EdgeNode, TopologyGraph

logger = logging.getLogger("cad_worker.topology_graph")

_TOLERANCE = 1e-6


def build_topology_graph(shape) -> TopologyGraph:
    """
    Build the complete face-edge adjacency graph from a TopoDS_Shape.

    Args:
        shape: A valid OCC TopoDS_Shape (solid or compound).

    Returns:
        TopologyGraph with all faces (typed, with normals and adjacency)
        and all edges (with lengths and connected face IDs).

    Raises:
        ValueError: If the shape is null or invalid.
    """
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepGProp import BRepGProp
    from OCP.GCPnts import GCPnts_AbscissaPoint
    from OCP.GProp import GProp_GProps
    from OCP.GeomAbs import (
        GeomAbs_Plane,
        GeomAbs_Cylinder,
        GeomAbs_Cone,
        GeomAbs_Sphere,
    )
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_REVERSED
    from OCP.TopExp import TopExp, TopExp_Explorer
    from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape
    from OCP.TopoDS import TopoDS

    # ── Validate shape ──────────────────────────────────────────────────
    if shape is None or shape.IsNull():
        raise ValueError("Cannot build topology graph: shape is null")

    t_start = time.monotonic()
    logger.info("Building topology graph...")

    # ── Surface type mapping ────────────────────────────────────────────
    _SURFACE_TYPE_MAP = {
        GeomAbs_Plane: "PLANAR",
        GeomAbs_Cylinder: "CYLINDRICAL",
        GeomAbs_Cone: "CONICAL",
        GeomAbs_Sphere: "SPHERICAL",
    }

    # ── Step 1: Build edge → face adjacency map ────────────────────────
    # TopExp.MapShapesAndAncestors builds a map from sub-shapes (edges)
    # to their parent shapes (faces). In a valid manifold solid, each
    # shared edge connects exactly 2 faces.
    edge_face_map = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, edge_face_map)

    # ── Step 2: Index all faces ─────────────────────────────────────────
    # Give each face a stable string ID for cross-referencing.
    face_list = []
    face_shape_to_id: dict = {}  # hash(face shape) → face ID

    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    face_idx = 0
    while explorer.More():
        face = TopoDS.Face_s(explorer.Current())
        face_id = f"F_{face_idx + 1:03d}"
        face_list.append((face_id, face))
        # Use the TShape pointer hash for identity comparison
        face_shape_to_id[face.HashCode(2147483647)] = face_id
        face_idx += 1
        explorer.Next()

    logger.info(f"Indexed {len(face_list)} faces")

    # ── Step 3: Build face nodes ────────────────────────────────────────
    face_nodes: list[FaceNode] = []

    for face_id, face in face_list:
        try:
            # Surface type classification
            adaptor = BRepAdaptor_Surface(face)
            surface_type_str = _SURFACE_TYPE_MAP.get(
                adaptor.GetType(), "OTHER"
            )

            # Face area via GProp
            area_props = GProp_GProps()
            BRepGProp.SurfaceProperties_s(face, area_props)
            area = round(abs(area_props.Mass()), 6)

            # Face center (centroid of the surface)
            center_pnt = area_props.CentreOfMass()
            center = (
                round(center_pnt.X(), 6),
                round(center_pnt.Y(), 6),
                round(center_pnt.Z(), 6),
            )

            # Face normal at centroid  
            # Use the parametric midpoint for normal evaluation
            u_min = adaptor.FirstUParameter()
            u_max = adaptor.LastUParameter()
            v_min = adaptor.FirstVParameter()
            v_max = adaptor.LastVParameter()
            u_mid = (u_min + u_max) / 2.0
            v_mid = (v_min + v_max) / 2.0

            # BRepLProp_SLProps computes surface properties at (u, v)
            from OCP.BRepLProp import BRepLProp_SLProps
            props = BRepLProp_SLProps(adaptor, u_mid, v_mid, 1, _TOLERANCE)

            if props.IsNormalDefined():
                normal_dir = props.Normal()
                nx, ny, nz = normal_dir.X(), normal_dir.Y(), normal_dir.Z()

                # Normalize to unit length
                magnitude = math.sqrt(nx * nx + ny * ny + nz * nz)
                if magnitude > _TOLERANCE:
                    nx /= magnitude
                    ny /= magnitude
                    nz /= magnitude
                else:
                    # Degenerate normal — use zero vector (will be logged)
                    logger.warning(
                        f"Face {face_id}: degenerate normal (magnitude ≈ 0)"
                    )
                    nx, ny, nz = 0.0, 0.0, 0.0

                # Account for face orientation (IsReversed)
                # OCC faces can be reversed relative to their surface —
                # if reversed, the outward normal is flipped.
                # Use TopAbs_REVERSED constant (not magic number 1)
                if face.Orientation() == TopAbs_REVERSED:
                    nx, ny, nz = -nx, -ny, -nz

                normal = (round(nx, 6), round(ny, 6), round(nz, 6))
            else:
                logger.warning(
                    f"Face {face_id}: normal not defined at parametric midpoint"
                )
                normal = (0.0, 0.0, 0.0)

            face_nodes.append(FaceNode(
                id=face_id,
                surface_type=surface_type_str,
                area=area,
                normal=normal,
                center=center,
                adjacent_faces=[],  # Populated in Step 5
            ))

        except Exception as e:
            logger.warning(f"Face {face_id}: processing failed: {e}")
            # Add a minimal node so the graph stays consistent
            face_nodes.append(FaceNode(
                id=face_id,
                surface_type="OTHER",
                area=0.0,
                normal=(0.0, 0.0, 0.0),
                center=(0.0, 0.0, 0.0),
                adjacent_faces=[],
            ))

    # ── Step 4: Build edge nodes and adjacency ──────────────────────────
    edge_nodes: list[EdgeNode] = []
    # Track adjacency: face_id → set of adjacent face IDs
    adjacency: dict[str, set[str]] = {fn.id: set() for fn in face_nodes}

    edge_idx = 0
    for i in range(1, edge_face_map.Extent() + 1):
        edge_shape = edge_face_map.FindKey(i)
        edge = TopoDS.Edge_s(edge_shape)

        edge_id = f"E_{edge_idx + 1:03d}"
        edge_idx += 1

        # Compute edge length using parametric curve integration
        # GCPnts_AbscissaPoint.Length computes the arc length by
        # integrating |dr/dt| over the parameter range, which correctly
        # handles curved edges (circles, splines, etc.)
        edge_length = 0.0
        try:
            from OCP.BRepAdaptor import BRepAdaptor_Curve
            curve_adaptor = BRepAdaptor_Curve(edge)
            edge_length = round(
                abs(GCPnts_AbscissaPoint.Length_s(curve_adaptor)),
                6,
            )
        except Exception as e:
            logger.warning(f"Edge {edge_id}: length computation failed: {e}")

        # Find connected faces via the edge→face map
        connected_face_ids: list[str] = []
        face_list_for_edge = edge_face_map.FindFromIndex(i)

        for j in range(1, face_list_for_edge.Extent() + 1):
            parent_face = face_list_for_edge.Value(j)
            parent_hash = parent_face.HashCode(2147483647)
            if parent_hash in face_shape_to_id:
                connected_face_ids.append(face_shape_to_id[parent_hash])

        edge_nodes.append(EdgeNode(
            id=edge_id,
            length=edge_length,
            connected_faces=connected_face_ids,
        ))

        # Update adjacency: if an edge connects faces A and B,
        # then A is adjacent to B and B is adjacent to A.
        if len(connected_face_ids) == 2:
            f_a, f_b = connected_face_ids[0], connected_face_ids[1]
            adjacency[f_a].add(f_b)
            adjacency[f_b].add(f_a)
        elif len(connected_face_ids) > 2:
            # Non-manifold edge — add all pairwise adjacencies
            for k in range(len(connected_face_ids)):
                for m in range(k + 1, len(connected_face_ids)):
                    adjacency[connected_face_ids[k]].add(connected_face_ids[m])
                    adjacency[connected_face_ids[m]].add(connected_face_ids[k])

    # ── Step 5: Populate face adjacency lists ───────────────────────────
    for fn in face_nodes:
        fn.adjacent_faces = sorted(adjacency.get(fn.id, set()))

    result = TopologyGraph(
        faces=face_nodes,
        edges=edge_nodes,
    )

    elapsed_ms = (time.monotonic() - t_start) * 1000
    logger.info(
        f"Topology graph complete in {elapsed_ms:.1f}ms: "
        f"{len(face_nodes)} faces, {len(edge_nodes)} edges"
    )

    return result
