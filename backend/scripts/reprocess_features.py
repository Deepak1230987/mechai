"""
Re-run feature detection for a model that has feature_ready=True but 0 features.
This can happen when the model was processed by the old processor (pre-worker pipeline).

Usage:
  cd backend
  python scripts/reprocess_features.py <model_id>
"""

import asyncio
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select, text
from shared.db.session import engine as async_engine, async_session_factory
from cad_service.models import CADModel
from cad_worker.models import ModelGeometry, ModelFeature
from cad_worker.geometry_engine import get_engine
from cad_worker.geometry_engine.feature_recognition import detect_all_features
from cad_worker.services.db_service import save_features
from shared.config import get_settings

settings = get_settings()


async def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/reprocess_features.py <model_id>")
        sys.exit(1)

    model_id = sys.argv[1]
    print(f"Re-processing features for model: {model_id}")

    async with async_session_factory() as session:
        # 1. Look up model
        result = await session.execute(
            select(CADModel).where(CADModel.id == model_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            print(f"ERROR: Model {model_id} not found!")
            sys.exit(1)

        print(f"  Name: {model.name}")
        print(f"  Format: {model.file_format}")
        print(f"  Status: {model.status}")
        print(f"  GCS Path: {model.gcs_path}")

        # 2. Find geometry record
        result = await session.execute(
            select(ModelGeometry).where(ModelGeometry.model_id == model_id)
        )
        geom = result.scalar_one_or_none()
        if geom:
            print(f"  Geometry: type={geom.geometry_type}, feature_ready={geom.feature_ready}")
            print(f"  Face counts: planar={geom.planar_faces}, cyl={geom.cylindrical_faces}")
        else:
            print("  Geometry: None (will be created)")

        # 3. Check existing features
        result = await session.execute(
            select(ModelFeature).where(ModelFeature.model_id == model_id)
        )
        existing = result.scalars().all()
        print(f"  Existing features: {len(existing)}")

        # 4. Find the source file
        gcs_path = model.gcs_path
        if not gcs_path:
            print("ERROR: model.gcs_path is empty — cannot find source file")
            sys.exit(1)

        # Resolve to local file path
        local_dir = os.path.join(
            os.path.dirname(__file__), "..", "local_uploads"
        )
        local_path = Path(os.path.join(local_dir, gcs_path))
        if not local_path.exists():
            print(f"ERROR: Source file not found at {local_path}")
            sys.exit(1)

        print(f"  Source file: {local_path}")

        # 5. Get geometry engine
        ext = local_path.suffix.lower()
        engine = get_engine(ext)
        print(f"  Engine: {engine.__class__.__name__}")

        # 6. Extract geometry (updates face counts too)
        print("\n  Extracting geometry...")
        geometry_result = await asyncio.to_thread(
            engine.extract_geometry, str(local_path)
        )
        print(f"  Geometry type: {geometry_result.geometry_type}")
        print(f"  Volume: {geometry_result.volume}")
        print(f"  Surface area: {geometry_result.surface_area}")
        print(f"  Planar faces: {geometry_result.planar_faces}")
        print(f"  Cylindrical faces: {geometry_result.cylindrical_faces}")
        print(f"  Feature ready: {geometry_result.feature_ready}")

        # 7. Update geometry record
        if geom:
            geom.volume = geometry_result.volume
            geom.surface_area = geometry_result.surface_area
            geom.bounding_box = geometry_result.bounding_box
            geom.planar_faces = geometry_result.planar_faces
            geom.cylindrical_faces = geometry_result.cylindrical_faces
            geom.conical_faces = geometry_result.conical_faces
            geom.spherical_faces = geometry_result.spherical_faces
            geom.feature_ready = geometry_result.feature_ready
            await session.commit()
            print("  Geometry record updated")

        # 8. Run feature detection (BRep only)
        if geometry_result.geometry_type == "BREP":
            print("\n  Running feature detection...")
            brep_shape = await asyncio.to_thread(engine.load_shape, local_path)
            feature_results = await asyncio.to_thread(
                detect_all_features, brep_shape
            )
            print(f"  Features detected: {len(feature_results)}")
            for f in feature_results:
                print(f"    - {f.type}: depth={f.depth}, dia={f.diameter}, conf={f.confidence}")

            if feature_results:
                # Delete old features first
                if existing:
                    for feat in existing:
                        await session.delete(feat)
                    await session.commit()
                    print(f"  Deleted {len(existing)} old features")

                feature_ids = await save_features(model_id, feature_results)
                print(f"  Saved {len(feature_ids)} new features")
            else:
                print("  No features detected on this model")
        else:
            print("  Skipping feature detection (not BRep)")

    print("\nDone!")


asyncio.run(main())
