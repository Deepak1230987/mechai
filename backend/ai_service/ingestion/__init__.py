"""Ingestion layer — fetches and adapts ManufacturingGeometryReport."""

from ai_service.ingestion.intelligence_client import fetch_model_intelligence
from ai_service.ingestion.intelligence_adapter import adapt_intelligence

__all__ = ["fetch_model_intelligence", "adapt_intelligence"]
