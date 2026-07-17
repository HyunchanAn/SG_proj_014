from pydantic import BaseModel, Field, field_validator, model_validator
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
    surface_energy: float = Field(..., ge=10.0, le=100.0, description="표면 자유 에너지 (SFE, mN/m). 물방울 접촉각을 통해 계산된 값.", json_schema_extra={"example": 96.43})
    roughness: float = Field(..., ge=0.0, description="표면 조도 (Ra, um).", json_schema_extra={"example": 0.13})
    gloss: float = Field(..., ge=0.0, le=2000.0, description="광택도 (GU).", json_schema_extra={"example": 100.0})
    curvature_radius: float = Field(..., description="곡률 반경 (R, mm). 3D 분석을 통해 도출.", json_schema_extra={"example": -0.0076})

    @field_validator("surface_energy")
    @classmethod
    def check_sfe(cls, v):
        # 계측 범위 및 고체 물리 화학적 실측 타당 범위 (10.0 ~ 100.0 mN/m) 보장
        if v < 10.0 or v > 100.0:
            raise ValueError("[에러] 물방울 접촉각 인식 이상 또는 물리 화학적 SFE 타당 한계치 초과 (허용치: 10.0 ~ 100.0 mN/m)")
        return v
    
    @field_validator("curvature_radius")
    @classmethod
    def check_curvature(cls, v):
        # 3D 곡률 해석을 위한 물리 최소 한계 곡률반경 (0.01mm) 정의
        if abs(v) < 0.01:
            raise ValueError("[에러] 곡률 반경이 물리적 연산 한계(0.01mm) 미만으로 극단적으로 작아 공정 해석이 불가능합니다.")
        return v

class Step2Target(BaseModel):
    target_initial_adhesion: float = Field(..., ge=0.0, description="목표 초기 점착력 (gf/25mm)", json_schema_extra={"example": 520.0})
    target_aged_adhesion: float = Field(..., ge=0.0, description="목표 후기 경시 점착력 (gf/25mm)", json_schema_extra={"example": 990.0})
    target_tg: float = Field(..., ge=-80.0, le=0.0, description="목표 유리전이온도 (Tg, °C)", json_schema_extra={"example": -20.0})
    target_viscosity: float = Field(..., ge=0.0, description="목표 점도 (cps)", json_schema_extra={"example": 3500.0})
    adhesion_test_angle: str = Field(default="90", description="점착력 테스트 박리 각도 (예: 90, 180)")
    adhesion_test_substrate: str = Field(default="BA", description="점착력 테스트 기재 (예: BA, SUS)")

    @field_validator("target_tg")
    @classmethod
    def check_tg(cls, v):
        # 아크릴계 보호 필름 점착 수지의 중합 물리 한계치 (-80 ~ 0 °C) 매핑
        if v < -80.0 or v > 0.0:
            raise ValueError("[에러] 입력된 Tg 수치는 보호필름 점착제 수지 합성 한계를 벗어납니다. (허용치: -80 ~ 0 °C)")
        return v
        
    @model_validator(mode='after')
    def check_adhesion_growth(self):
        if self.target_initial_adhesion > self.target_aged_adhesion:
            from loguru import logger
            logger.error("[DOMAIN ERROR] 물리적 경시 상승 법칙 위배 인입 건 차단")
            raise ValueError("초기 점착력이 후기 경시 점착력보다 클 수 없습니다.")
        return self

class OrchestrationRequest(BaseModel):
    substrate_id: str = Field(..., description="피착재 고유 ID", json_schema_extra={"example": "SUB_75BFJ"})
    substrate_series: str = Field(..., description="기재 계열 (예: SGV, SGO, SGE)", json_schema_extra={"example": "SGV"})
    thickness_um: float = Field(..., description="기재 두께 (um)", json_schema_extra={"example": 100.0})
    finish_type: str = Field(..., description="마감 종류 (예: Hairline, Mirror)", json_schema_extra={"example": "Hairline"})
    metrics: Step1Metrics
    target: Step2Target
    normal_vector_data: list[float] = Field(..., description="3D 법선 벡터 데이터 시퀀스", json_schema_extra={"example": [0.1, 0.2, 0.9]})
    material_stiffness: float = Field(..., description="소재 강성 (MPa)", json_schema_extra={"example": 200000.0})
