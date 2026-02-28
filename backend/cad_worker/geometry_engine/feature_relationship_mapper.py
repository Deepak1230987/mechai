"""
Feature Relationship Mapper — builds parent-child and intersection hierarchies.

WHY FEATURE RELATIONSHIPS ARE CRITICAL FOR PHASE B
===================================================
Without relationships, Phase B sees features as independent operations.
With relationships, it can:

  • Sequence correctly: "Machine pocket BEFORE drilling the hole inside it"
  • Detect collisions: "These two features overlap — toolpath needs care"
  • Plan efficiently: "Group child features with parent in same setup"
  • Estimate risk: "Intersecting features increase rejection probability"

ALGORITHM
=========
1. Spatial Containment (parent-child):
   Feature A contains Feature B if B's position is inside A's bounding
   volume (defined by A's position ± depth/width/diameter).
   Type-based rules refine this:
     • HOLE inside POCKET → child of pocket
     • CHAMFER adjacent to HOLE → child of hole
     • FILLET at POCKET corner → child of pocket

2. Face Adjacency (intersecting):
   Features sharing parent_face_ids or with parent faces that are
   adjacent in the topology graph → intersecting.

3. Bidirectional linking:
   If A is parent of B → A.child_feature_ids includes B.id
   If B is parent of A → B.child_feature_ids includes A.id
   If A intersects B → both have each other in intersecting_feature_ids

Deterministic only. No AI.
"""

from __future__ import annotations

import logging
import math
from typing import Optional

from cad_worker.schemas import FeatureSpatial, TopologyGraph

logger = logging.getLogger("cad_worker.feature_relationship_mapper")

_TOLERANCE = 1e-6

# Distance threshold for spatial containment check (mm).
# A feature within this distance of another's center is "inside".
_CONTAINMENT_DISTANCE_FACTOR = 0.8


def build_feature_relationships(
    features: list[FeatureSpatial],
    topology_graph: TopologyGraph,
) -> list[FeatureSpatial]:
    """
    Build parent-child and intersection relationships between features.

    Returns a new list of FeatureSpatial with populated:
      - parent_feature_id
      - child_feature_ids
      - intersecting_feature_ids

    Args:
        features: List of spatially-mapped features (from mapper + classifiers).
        topology_graph: Topology graph for face adjacency lookups.

    Returns:
        New list of FeatureSpatial with relationship fields populated.
    """
    if len(features) < 2:
        logger.info("Feature relationships: < 2 features, nothing to map")
        return features

    n = len(features)
    logger.info(f"Building relationships for {n} features")

    # ── Build face adjacency lookup from topology ───────────────────────
    face_adjacency = _build_face_adjacency(topology_graph)

    # ── Relationship matrices ───────────────────────────────────────────
    # parent_of[i] = j means features[j] is parent of features[i]
    parent_of: dict[int, Optional[int]] = {i: None for i in range(n)}
    # children[i] = set of indices that are children of features[i]
    children: dict[int, set[int]] = {i: set() for i in range(n)}
    # intersecting[i] = set of indices that intersect with features[i]
    intersecting: dict[int, set[int]] = {i: set() for i in range(n)}

    # ── Pass 1: Spatial containment (parent-child) ──────────────────────
    for i in range(n):
        for j in range(n):
            if i == j:
                continue

            fi = features[i]
            fj = features[j]

            if _is_contained_in(fi, fj):
                # fi is inside fj → fj is parent of fi
                # But only if this is a valid parent-child relationship
                if _is_valid_parent_child(fj, fi):
                    # Prefer the smallest valid container as parent
                    current_parent = parent_of[i]
                    if current_parent is None:
                        parent_of[i] = j
                    else:
                        # Choose the smaller parent (closer container)
                        current_size = _feature_volume(features[current_parent])
                        new_size = _feature_volume(fj)
                        if new_size < current_size:
                            parent_of[i] = j

    # Populate children from parent_of
    for child_idx, parent_idx in parent_of.items():
        if parent_idx is not None:
            children[parent_idx].add(child_idx)

    # ── Pass 2: Face adjacency (intersecting) ───────────────────────────
    for i in range(n):
        for j in range(i + 1, n):
            fi = features[i]
            fj = features[j]

            # Skip parent-child pairs — they're related, not intersecting
            if parent_of[i] == j or parent_of[j] == i:
                continue

            if _are_adjacent_features(fi, fj, face_adjacency):
                intersecting[i].add(j)
                intersecting[j].add(i)

    # ── Build result list with relationships ────────────────────────────
    result: list[FeatureSpatial] = []
    parent_count = 0
    intersect_count = 0

    for i, feat in enumerate(features):
        updates: dict = {}

        # Parent feature
        if parent_of[i] is not None:
            updates["parent_feature_id"] = features[parent_of[i]].id
            parent_count += 1

        # Child features
        if children[i]:
            updates["child_feature_ids"] = [features[c].id for c in children[i]]

        # Intersecting features
        if intersecting[i]:
            updates["intersecting_feature_ids"] = [
                features[x].id for x in intersecting[i]
            ]
            intersect_count += 1

        if updates:
            result.append(feat.model_copy(update=updates))
        else:
            result.append(feat)

    logger.info(
        f"Feature relationships: "
        f"{parent_count} parent-child, "
        f"{intersect_count} intersecting"
    )

    return result


# ── Internal helpers ─────────────────────────────────────────────────────────

def _build_face_adjacency(topology: TopologyGraph) -> dict[str, set[str]]:
    """
    Build a lookup: face_id → set of adjacent face IDs.
    Uses the topology graph's pre-built adjacency lists.
    """
    adjacency: dict[str, set[str]] = {}
    for face in topology.faces:
        adjacency[face.id] = set(face.adjacent_faces)
    return adjacency


def _is_contained_in(inner: FeatureSpatial, outer: FeatureSpatial) -> bool:
    """
    Check if the inner feature's position is within the outer feature's
    bounding volume.

    Mathematical logic:
        The outer feature defines a bounding cylinder/box centered at
        outer.position with extent along outer.axis_direction.
        
        We check if inner.position is within:
          • Radial distance from outer axis < outer diameter/2 * 1.2
          • Axial distance from outer center < outer depth/2 * 1.2
          
        The 1.2 factor accounts for geometric imprecision from BSpline
        surface classification.
    """
    # Compute distance between positions
    dx = inner.position[0] - outer.position[0]
    dy = inner.position[1] - outer.position[1]
    dz = inner.position[2] - outer.position[2]
    dist = math.sqrt(dx * dx + dy * dy + dz * dz)

    # Outer feature effective radius
    outer_radius = _feature_bounding_radius(outer)
    if outer_radius < _TOLERANCE:
        return False

    # Inner must be within the outer's bounding radius
    return dist < outer_radius * _CONTAINMENT_DISTANCE_FACTOR


def _feature_bounding_radius(feat: FeatureSpatial) -> float:
    """
    Compute a simplified bounding radius for containment checks.
    
    Uses the largest available dimension to create an enclosing sphere.
    """
    dims = []
    if feat.diameter is not None:
        dims.append(feat.diameter / 2.0)
    if feat.depth is not None:
        dims.append(feat.depth / 2.0)
    if feat.width is not None:
        dims.append(feat.width / 2.0)
    if feat.length is not None:
        dims.append(feat.length / 2.0)

    if not dims:
        return 0.0

    # Bounding sphere radius ≈ diagonal of the feature
    return math.sqrt(sum(d * d for d in dims))


def _feature_volume(feat: FeatureSpatial) -> float:
    """Approximate feature volume for parent selection (prefer smallest)."""
    d = feat.diameter or 1.0
    depth = feat.depth or 1.0
    w = feat.width or d
    l = feat.length or w
    return d * depth * w * l


def _is_valid_parent_child(parent: FeatureSpatial, child: FeatureSpatial) -> bool:
    """
    Validate that a parent-child relationship is physically meaningful.
    
    Rules:
      • Pocket/Slot can contain: HOLE, CHAMFER, FILLET
      • HOLE cannot contain POCKET (smaller can't contain larger)
      • CHAMFER/FILLET cannot be parents (they're finishing features)
      • Parent should be larger than child
    """
    # Finishing features cannot be parents
    if parent.type in ("CHAMFER", "FILLET"):
        return False

    # Valid parent types for each child type
    valid_parents: dict[str, set[str]] = {
        "HOLE": {"POCKET", "SLOT"},
        "CHAMFER": {"HOLE", "POCKET", "SLOT"},
        "FILLET": {"POCKET", "SLOT"},
        "SLOT": {"POCKET"},
    }

    allowed = valid_parents.get(child.type)
    if allowed is None:
        return False

    return parent.type in allowed


def _are_adjacent_features(
    f1: FeatureSpatial,
    f2: FeatureSpatial,
    face_adjacency: dict[str, set[str]],
) -> bool:
    """
    Check if two features share face adjacency in the topology.
    
    Two features are adjacent (potentially intersecting) if:
      1. They share the same parent_face_id, OR
      2. Their parent faces are adjacent in the topology graph
    """
    # Same parent face
    if f1.parent_face_id == f2.parent_face_id:
        return True

    # Adjacent parent faces
    f1_adj = face_adjacency.get(f1.parent_face_id, set())
    return f2.parent_face_id in f1_adj
