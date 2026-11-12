"""AI intelligence endpoints (phase 3). Thin handlers: validate, delegate to AIService, return a schema.

All outputs are experimental decision support built on simulated data, never diagnoses.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.ai.service import AIService
from app.core.errors import ForbiddenError
from app.schemas.ai import (
    AIStatus,
    AlertExplanationResponse,
    AnomalyDetectionRequest,
    AnomalyDetectionResponse,
    BaselineResponse,
    CrewRiskOverview,
    ForecastResponse,
    ModelPerformanceResponse,
    RiskAssessmentResponse,
)
from app.schemas.common import ERROR_RESPONSES, ErrorResponse

UNAVAILABLE = {503: {"model": ErrorResponse, "description": "No trained model version is available"}}
NOT_ENOUGH = {409: {"model": ErrorResponse, "description": "Not enough stored data"}}

router = APIRouter(prefix="/api/ai", tags=["ai"], responses=ERROR_RESPONSES)


def get_ai(request: Request) -> AIService:
    return request.app.state.ai


AI = Annotated[AIService, Depends(get_ai)]


@router.get("/status", response_model=AIStatus)
async def ai_status(ai: AI) -> AIStatus:
    """Which model version is loaded, and which detectors and forecasters it provides."""
    return AIStatus.model_validate(await ai.status())


@router.post("/anomaly-detection", response_model=AnomalyDetectionResponse, responses={**UNAVAILABLE, **NOT_ENOUGH})
async def anomaly_detection(body: AnomalyDetectionRequest, ai: AI) -> AnomalyDetectionResponse:
    """Score stored windows (default: last 6 h) or supplied readings with the anomaly ensemble.

    Returns a per-window timeline (each detector's calibrated score, ensemble score, votes), the
    flagged segments that persist for at least 10 minutes, and an explanation for each.
    """
    return AnomalyDetectionResponse.model_validate(await ai.detect(body))


@router.get("/astronaut/{astronaut_id}/baseline", response_model=BaselineResponse, responses=NOT_ENOUGH)
async def baseline(astronaut_id: str, ai: AI) -> BaselineResponse:
    """Personal baseline per signal (by activity and time of day), rolling statistics, and how the
    latest reading compares."""
    return BaselineResponse.model_validate(await ai.baseline_report(astronaut_id))


@router.get("/astronaut/{astronaut_id}/forecast", response_model=ForecastResponse, responses={**UNAVAILABLE, **NOT_ENOUGH})
async def forecast(
    astronaut_id: str,
    ai: AI,
    model: Annotated[str | None, Query(description="xgboost (default), lstm, gru, tcn or a baseline")] = None,
    signals: Annotated[list[str] | None, Query(description="heart_rate, spo2, respiratory_rate, temperature_c")] = None,
) -> ForecastResponse:
    """24 h forecast in 30-minute steps with 90% split-conformal intervals and 1/6/12/24 h summaries."""
    return ForecastResponse.model_validate(await ai.forecast(astronaut_id, model, signals))


@router.get("/astronaut/{astronaut_id}/risk-assessment", response_model=RiskAssessmentResponse, responses=NOT_ENOUGH)
async def risk_assessment(astronaut_id: str, ai: AI) -> RiskAssessmentResponse:
    """Rule-based concern level with prioritised warnings and the measurements behind each."""
    return RiskAssessmentResponse.model_validate(await ai.risk(astronaut_id))


@router.get("/crew-overview", response_model=CrewRiskOverview)
async def crew_overview(ai: AI) -> CrewRiskOverview:
    """Risk summary and health score for every crew member, highest concern first."""
    return CrewRiskOverview.model_validate(await ai.crew_overview())


@router.get("/model-performance", response_model=ModelPerformanceResponse, responses=UNAVAILABLE)
async def model_performance(ai: AI) -> ModelPerformanceResponse:
    """Evaluation results of the loaded model version (simulated test split), ablations and limitations."""
    return ModelPerformanceResponse.model_validate(await ai.performance())


@router.get("/explanations/{alert_id}", response_model=AlertExplanationResponse, responses=NOT_ENOUGH)
async def explain_alert(alert_id: str, ai: AI) -> AlertExplanationResponse:
    """Why an alert fired: the rule, the contributing signals and how far each was from baseline."""
    return AlertExplanationResponse.model_validate(await ai.explain_alert(alert_id))


@router.post("/models/reload", response_model=AIStatus, responses={403: {"model": ErrorResponse}})
async def reload_models(ai: AI) -> AIStatus:
    """Load the newest registered model version (after running the training script)."""
    if not ai.settings.simulation_control_enabled:
        raise ForbiddenError("Operator controls are disabled on this deployment.")
    await ai.reload()
    return AIStatus.model_validate(await ai.status())
