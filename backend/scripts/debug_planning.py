"""Debug the planning pipeline step by step."""
import asyncio
import sys
import json
sys.path.insert(0, ".")

from shared.db.session import async_session_factory
from sqlalchemy import select
from cad_worker.models import ModelGeometry, ModelFeature
from cad_service.models.cad_model import CADModel

MODEL_ID = sys.argv[1] if len(sys.argv) > 1 else "0af7d876-d89b-4d0f-9d66-38b11c8626db"
MATERIAL = "ALUMINUM_6061"
MACHINE_TYPE = "MILLING_3AXIS"

async def main():
    async with async_session_factory() as session:
        # 1. Load features
        feat_result = await session.execute(
            select(ModelFeature).where(ModelFeature.model_id == MODEL_ID)
        )
        features_db = feat_result.scalars().all()
        print(f"Features in DB: {len(features_db)}")
        
        raw_features = []
        for f in features_db:
            feat = {
                "id": f.id,
                "type": f.type,
                "confidence": getattr(f, "confidence", 1.0),
                "dimensions": f.dimensions or {},
                "depth": f.depth,
                "diameter": f.diameter,
                "axis": f.axis,
            }
            raw_features.append(feat)
            print(f"  Feature: id={f.id}, type={f.type}, depth={f.depth}, dia={f.diameter}, conf={getattr(f, 'confidence', None)}")

        # 2. Load geometry  
        geom_result = await session.execute(
            select(ModelGeometry).where(ModelGeometry.model_id == MODEL_ID)
        )
        geom = geom_result.scalars().first()
        geometry_metadata = {
            "volume": geom.volume,
            "surface_area": geom.surface_area,
            "bounding_box": geom.bounding_box or {},
            "planar_faces": geom.planar_faces,
            "cylindrical_faces": geom.cylindrical_faces,
            "conical_faces": geom.conical_faces, 
            "spherical_faces": geom.spherical_faces,
        }
        print(f"\nGeometry: {json.dumps(geometry_metadata, indent=2, default=str)}")

        # 3. Validate features
        from ai_service.services.feature_validator.deterministic_validator import DeterministicFeatureValidator
        validator = DeterministicFeatureValidator()
        validated = validator.validate(raw_features, geometry_metadata)
        print(f"\nValidated features: {len(validated)}")
        for v in validated:
            print(f"  {v['id']}: type={v['type']}, depth={v.get('depth')}")

        # 4. Rule engine
        from ai_service.services.rule_engine import plan_operations
        planned_ops = plan_operations(validated, MATERIAL, MACHINE_TYPE)
        print(f"\nPlanned operations: {len(planned_ops)}")
        for op in planned_ops:
            print(f"  op={op.id}, type={op.op_type}, feature={op.feature_id}, tool={op.tool.id if op.tool else None}")

        # 5. Build plan dict (simplified)
        from ai_service.schemas.planning import ToolSpec, OperationSpec, SetupSpec, MachiningPlanResponse
        from ai_service.services.time_estimator import estimate_operation_time, estimate_total_time
        from ai_service.services.setup_grouper import group_into_setups

        tool_map = {}
        for op in planned_ops:
            if op.tool and op.tool.id not in tool_map:
                tool_map[op.tool.id] = ToolSpec(
                    id=op.tool.id,
                    type=op.tool.type,
                    diameter=op.tool.diameter,
                    max_depth=op.tool.max_depth,
                    recommended_rpm_min=op.tool.rpm_min,
                    recommended_rpm_max=op.tool.rpm_max,
                )

        operation_specs = []
        operation_times = []
        for op in planned_ops:
            tool_type = op.tool.type if op.tool else "FLAT_END_MILL"
            tool_dia = op.tool.diameter if op.tool else 10.0
            tool_id = op.tool.id if op.tool else "unknown"
            t = estimate_operation_time(
                op_type=op.op_type,
                tool_type=tool_type,
                tool_diameter=tool_dia,
                material=MATERIAL,
                parameters=op.parameters,
            )
            operation_times.append(t)
            operation_specs.append(OperationSpec(
                id=op.id,
                feature_id=op.feature_id,
                type=op.op_type,
                tool_id=tool_id,
                parameters=op.parameters,
                estimated_time=round(t, 2),
            ))

        total_time = round(estimate_total_time(operation_times), 2)
        setup_dicts = group_into_setups(planned_ops, MACHINE_TYPE)
        setup_specs = [
            SetupSpec(setup_id=s["setup_id"], orientation=s["orientation"], operations=s["operations"])
            for s in setup_dicts
        ]

        base_plan = MachiningPlanResponse(
            model_id=MODEL_ID,
            material=MATERIAL,
            machine_type=MACHINE_TYPE,
            setups=setup_specs,
            operations=operation_specs,
            tools=list(tool_map.values()),
            estimated_time=total_time,
            version=1,
            approved=False,
        )
        base_dict = base_plan.model_dump()
        print(f"\nBase plan: {len(base_dict['operations'])} ops, {len(base_dict['tools'])} tools, {len(base_dict['setups'])} setups, time={base_dict['estimated_time']}")

        # 6. Validate
        from ai_service.services.plan_validator import PlanValidator, PlanValidationError
        pv = PlanValidator(validated, MATERIAL, MACHINE_TYPE)
        try:
            result = pv.validate(base_dict)
            print("\nPlan PASSED validation!")
        except PlanValidationError as e:
            print(f"\nPlan FAILED validation: {e.errors}")

asyncio.run(main())
