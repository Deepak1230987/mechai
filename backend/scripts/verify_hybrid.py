"""Quick import verification for hybrid pipeline components."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

checks = [
    ("FeatureValidator ABC",
     "from ai_service.services.feature_validator import FeatureValidator"),
    ("DeterministicFeatureValidator",
     "from ai_service.services.feature_validator.deterministic_validator import DeterministicFeatureValidator"),
    ("VertexFeatureValidator stub",
     "from ai_service.services.feature_validator.vertex_validator import VertexFeatureValidator"),
    ("ValidationLogger",
     "from ai_service.services.feature_validator.validation_logger import ValidationLogger"),
    ("LangChain pipeline",
     "from ai_service.services.langchain_pipeline import optimize_plan"),
    ("PlanValidator + Error",
     "from ai_service.services.plan_validator import PlanValidator, PlanValidationError"),
    ("MachiningPlan model (version)",
     "from ai_service.models import MachiningPlan; assert hasattr(MachiningPlan, 'version')"),
    ("MachiningPlan model (approved)",
     "from ai_service.models import MachiningPlan; assert hasattr(MachiningPlan, 'approved')"),
    ("FeatureValidationLog model",
     "from ai_service.models import FeatureValidationLog"),
    ("MachiningPlanResponse (version)",
     "from ai_service.schemas.machining_plan import MachiningPlanResponse; assert 'version' in MachiningPlanResponse.model_fields"),
    ("MachiningPlanResponse (approved)",
     "from ai_service.schemas.machining_plan import MachiningPlanResponse; assert 'approved' in MachiningPlanResponse.model_fields"),
    ("planning_service generate_plan",
     "from ai_service.services.planning_service import generate_plan"),
    ("planning route",
     "from ai_service.routes.planning import planning_router"),
    ("rule_engine",
     "from ai_service.services.rule_engine import plan_operations, group_into_setups"),
    ("time_estimator",
     "from ai_service.services.time_estimator import estimate_operation_time, estimate_total_time"),
    ("tool_library",
     "from ai_service.services.tool_library import ToolLibrary"),
    # ── Human-in-Loop additions ──
    ("MachiningPlan (approved_by)",
     "from ai_service.models import MachiningPlan; assert hasattr(MachiningPlan, 'approved_by')"),
    ("MachiningPlan (approved_at)",
     "from ai_service.models import MachiningPlan; assert hasattr(MachiningPlan, 'approved_at')"),
    ("PlanFeedback model",
     "from ai_service.models import PlanFeedback"),
    ("feedback_service",
     "from ai_service.services.feedback_service import calculate_diff, apply_edit, approve_plan, get_latest_plan"),
    ("PlanUpdateRequest schema",
     "from ai_service.schemas.machining_plan import PlanUpdateRequest"),
    ("PlanApproveRequest schema",
     "from ai_service.schemas.machining_plan import PlanApproveRequest"),
    ("PlanDiff schema",
     "from ai_service.schemas.machining_plan import PlanDiff"),
    ("PlanUpdateResponse schema",
     "from ai_service.schemas.machining_plan import PlanUpdateResponse"),
    ("MachiningPlanResponse (approved_by)",
     "from ai_service.schemas.machining_plan import MachiningPlanResponse; assert 'approved_by' in MachiningPlanResponse.model_fields"),
]

passed = 0
for name, stmt in checks:
    try:
        exec(stmt)
        print(f"  OK  {name}")
        passed += 1
    except Exception as e:
        print(f"FAIL  {name}: {e}")

print(f"\n{passed}/{len(checks)} passed")
