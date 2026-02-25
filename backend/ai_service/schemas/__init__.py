"""
AI Service schemas — request / response contracts.
"""

from ai_service.schemas.machining_plan import (
    PlanningRequest,
    ToolSpec,
    OperationSpec,
    SetupSpec,
    MachiningPlanResponse,
)

__all__ = [
    "PlanningRequest",
    "ToolSpec",
    "OperationSpec",
    "SetupSpec",
    "MachiningPlanResponse",
]
