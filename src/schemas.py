from pydantic import BaseModel, Field, field_validator
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

# Orchestrator Request (Refactored for SI Handover)
class Step1Metrics(BaseModel):
    surface_energy: float = Field(..., description="표면 자유 에너지 (SFE, mN/m). 물방울 접촉각을 통해 계산된 값.", example=96.43)
    roughness: float = Field(..., description="표면 조도 (Ra, um).", example=0.13)
    gloss: float = Field(..., description="광택도 (GU).", example=100.0)
    curvature_radius: float = Field(..., description="곡률 반경 (R, mm). 3D 분석을 통해 도출.", example=-0.0076)

    @field_validator("surface_energy")
    @classmethod
    def check_sfe(cls, v):
        # TODO: 임의로 설정된 한계값이므로 도메인 전문가의 검증 필요 (임의 값 입력했다)
        if v <= 0 or v >= 150:
            raise ValueError("물방울 인식이 실패하였거나 물리적 범위를 초과했습니다. (임의 설정된 SFE 한계치: 0 ~ 150)")
        return v
    
    @field_validator("curvature_radius")
    @classmethod
    def check_curvature(cls, v):
        # TODO: 임의 설정값
        if abs(v) < 0.000001:
            raise ValueError("곡률 반경이 극단적으로 작아 연산이 불가합니다. (임의 설정치)")
        return v

class Step2Target(BaseModel):
    target_adhesion: float = Field(..., description="목표 점착력 (gf/25mm)", example=1200.0)
    target_tg: float = Field(..., description="목표 유리전이온도 (Tg, °C)", example=-20.0)
    target_viscosity: float = Field(..., description="목표 점도 (cps)", example=3500.0)

    @field_validator("target_tg")
    @classmethod
    def check_tg(cls, v):
        # TODO: 임의로 설정된 한계값이므로 도메인 전문가의 검증 필요 (임의 값 입력했다)
        if v < -100 or v > 200:
            raise ValueError("해당 배합(Tg)은 물리적으로 불안정합니다. (임의 설정된 Tg 한계치: -100 ~ 200)")
        return v

class OrchestrationRequest(BaseModel):
    substrate_id: str = Field(..., description="피착재 고유 ID", example="SUB_75BFJ")
    finish_type: str = Field(..., description="마감 종류 (예: Hairline, Mirror)", example="Hairline")
    metrics: Step1Metrics
    target: Step2Target
    normal_vector_data: list[float] = Field(..., description="3D 법선 벡터 데이터 시퀀스", example=[0.1, 0.2, 0.9])
    material_stiffness: float = Field(..., description="소재 강성 (MPa)", example=200000.0)
