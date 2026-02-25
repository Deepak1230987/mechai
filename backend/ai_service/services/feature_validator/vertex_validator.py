"""
Vertex AI Feature Validator — STUB.

This will be the ML-powered validator that uses a trained model on
Vertex AI to predict feature validity from geometry embeddings.

NOT YET IMPLEMENTED.  Raises NotImplementedError on all calls.

When ready:
    1. Train a model on data from feature_validation_logs
    2. Deploy to Vertex AI endpoint
    3. Implement predict() call here
    4. Swap DeterministicFeatureValidator → VertexFeatureValidator in config
"""

from __future__ import annotations

from ai_service.services.feature_validator import FeatureValidator


class VertexFeatureValidator(FeatureValidator):
    """
    ML-powered feature validator using Google Vertex AI.

    Stub only — raises NotImplementedError.
    """

    def validate(
        self,
        features: list[dict],
        geometry_metadata: dict,
    ) -> list[dict]:
        """
        Validate features using a Vertex AI model.

        Not yet implemented.  When ready, this will:
            1. Serialize features + geometry into model input format
            2. Call Vertex AI prediction endpoint
            3. Filter / re-score features based on model output
            4. Return validated list
        """
        raise NotImplementedError(
            "VertexFeatureValidator is not yet implemented. "
            "Use DeterministicFeatureValidator until the ML model is trained "
            "and deployed to Vertex AI."
        )
