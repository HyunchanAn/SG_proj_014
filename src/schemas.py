from pydantic import BaseModel, Field
from typing import Optional

# SG_proj_011
class TopographyInput(BaseModel):
    normal_vector_data: list[float]
    curvature_radius: float
    material_stiffness: float
    
class ProcessabilityResult(BaseModel):
    level: int = Field(ge=1, le=5, description="1(가장 유연) ~ 5(매우 단단함)")
    is_fallback: bool = Field(default=False, description="경계값/에러로 인한 기본값 사용 여부")
    reason: str

# SG_proj_012
class MatchingRequest(BaseModel):
    substrate_id: str
    surface_energy: float
    roughness: float
    finish_type: str
    required_processability_level: int

class ProductRecommendation(BaseModel):
    product_code: str
    match_score: float
    match_reason: dict

class MatchingResponse(BaseModel):
    recommendations: list[ProductRecommendation] = Field(max_length=3)
    is_successful: bool

# SG_proj_013
class ReverseEngineeringInput(BaseModel):
    target_properties: dict
    xgboost_prediction: dict
    ir_gnn_features: list[float]
    current_iteration: int = Field(default=1, ge=1, le=5)
    
class VerificationResult(BaseModel):
    is_passed: bool
    predicted_properties: dict
    error_rates: dict
    confidence_score: float
    feedback_signal: Optional[dict] = Field(None, description="오차 초과 시 보정 파라미터 제안")

# Orchestrator Request
class OrchestrationRequest(BaseModel):
    substrate_id: str
    surface_energy: float
    roughness: float
    finish_type: str
    normal_vector_data: list[float]
    curvature_radius: float
    material_stiffness: float
