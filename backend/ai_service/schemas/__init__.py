"""
AI Service schemas — request / response contracts.
"""

from ai_service.schemas.machining_plan import (
    PlanningRequest,
    ToolSpec,
    OperationSpec,
    SetupSpec,
    MachiningPlanResponse,
    PlanUpdateRequest,
    PlanApproveRequest,
    PlanDiff,
    PlanUpdateResponse,
)

__all__ = [
    "PlanningRequest",
    "ToolSpec",
    "OperationSpec",
    "SetupSpec",
    "MachiningPlanResponse",
    "PlanUpdateRequest",
    "PlanApproveRequest",
    "PlanDiff",
    "PlanUpdateResponse",
]
