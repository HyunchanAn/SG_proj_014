import pytest
import httpx
import respx
from httpx import Response
from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.orm import declarative_base, sessionmaker
import logging

from src.main import app
from fastapi.testclient import TestClient

logger = logging.getLogger(__name__)

Base = declarative_base()

class Adherend(Base):
    __tablename__ = 'adherends'
    id = Column(Integer, primary_key=True)
    product_name = Column(String)
    classification = Column(String)
    surface_energy_md = Column(Float)
    roughness_md = Column(Float)
    gloss_md = Column(Float)
    thickness_mm = Column(Float)

@pytest.fixture(scope="function")
def in_memory_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    
    # 더미 가상 피착재 데이터 주입 (SUS, PCM/VCM)
    sus_data = Adherend(
        product_name="SUS_304",
        classification="Hairline",
        surface_energy_md=45.0,
        roughness_md=0.15,
        gloss_md=150.0,
        thickness_mm=0.5
    )
    session.add(sus_data)
    session.commit()
    
    yield session
    
    session.close()

@pytest.mark.anyio
@respx.mock
async def test_full_pipeline_e2e_in_memory(in_memory_db):
    """
    1. 인메모리 DB에서 004 라우팅 호출을 가로채어 SUS 데이터를 응답.
    2. 011, 012, 013, 비전 모듈들의 외부 호출을 respx로 모킹.
    3. Target Adhesion을 5000 등 극한 스펙으로 주입.
    4. 012 매칭 실패 -> 013 역설계 성공(status: reverse_engineered) 이행 검증.
    """
    
    # 004 DB 모듈 검색 API 모킹
    def db_search_handler(request):
        # 인메모리 DB를 찔러 결과를 반환
        result = in_memory_db.query(Adherend).first()
        if result:
            return Response(200, json=[{
                "product_name": result.product_name,
                "classification": result.classification,
                "surface_energy_md": result.surface_energy_md,
                "roughness_md": result.roughness_md,
                "gloss_md": result.gloss_md,
                "thickness_mm": result.thickness_mm
            }])
        return Response(200, json=[])

    respx.get(url__regex=r"http://localhost:8004/adherends/search.*").mock(side_effect=db_search_handler)
    
    # 비전 모듈 002, 003, 007 모킹
    respx.post(url__regex=r"http://.*/analyze/image").mock(return_value=Response(200, json={"surface_energy": 45.0}))
    respx.post(url__regex=r"http://.*/analyze/roughness").mock(return_value=Response(200, json={"roughness": 0.15, "gloss": 150.0}))
    respx.post(url__regex=r"http://.*/api/v1/analyze").mock(return_value=Response(200, json={"metrics": {"estimated_radius_mm": 1.5}}))
    
    # 011 Processability 모킹
    respx.post(url__regex=r"http://.*/calculate_processability").mock(
        return_value=Response(200, json={"level": 3, "is_fallback": False, "reason": "Mocked processing"})
    )
    
    # 012 Matching 모킹 (매칭 실패 상황 강제 유도: Target Adhesion 5000)
    respx.post(url__regex=r"http://.*/match").mock(
        return_value=Response(200, json={"recommendations": [], "is_successful": False})
    )
    
    # 013 Reverse Engineering 모킹 (역설계 성공 상태 반환)
    # 실제 오케스트레이터 코드는 httpx.AsyncClient를 쓰기 때문에 httpx 요청이 가로채집니다.
    respx.post(url__regex=r"http://.*/optimize").mock(
        return_value=Response(200, json={"recipe": {"M1": 0.5, "M2": 0.5}, "predicted_properties": {"측정_값": 4800.0}})
    )
    respx.post(url__regex=r"http://.*/predict").mock(
        return_value=Response(200, json={"transmittance": [0.1, 0.2, 0.3]})
    )
    respx.post(url__regex=r"http://.*/verify").mock(
        return_value=Response(200, json={
            "is_passed": True, 
            "predicted_properties": {"측정_값": 4900.0, "Tg": -15.0}, 
            "error_rates": {}, 
            "confidence_score": 0.95
        })
    )

    # 014 내부 로직 테스트를 위한 AsyncClient (실제 앱에 연결)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 먼저 모킹된 004 API를 찔러 피착재 정보 가져오기 시뮬레이션
        db_res = httpx.get("http://localhost:8004/adherends/search?roughness_md_max=1.0")
        target_adherend = db_res.json()[0]
        
        payload = {
            "substrate_id": target_adherend["product_name"],
            "substrate_series": "SGV",
            "thickness_um": 100.0,
            "finish_type": target_adherend["classification"],
            "metrics": {
                "surface_energy": target_adherend["surface_energy_md"],
                "roughness": target_adherend["roughness_md"],
                "gloss": target_adherend["gloss_md"],
                "curvature_radius": 1.0 # mock thickness as radius
            },
            "target": {
                "target_initial_adhesion": 5000.0,  # 극한 스펙 주입
                "target_aged_adhesion": 5500.0,
                "target_tg": -20.0,
                "target_viscosity": 3500.0
            },
            "normal_vector_data": [0.01, 0.02, 0.01],
            "material_stiffness": 180.0
        }
        
        # 오케스트레이터 API 호출
        orch_res = await client.post("/orchestrate", json=payload)
        
        assert orch_res.status_code == 200, f"오케스트레이터 오류: {orch_res.text}"
        result_data = orch_res.json()
        
        # 비즈니스 어설션: 극한 스펙(5000.0)으로 매칭은 실패해야 하고, 역설계로 전환되어야 함
        assert result_data["status"] == "reverse_engineered", "오케스트레이터가 reverse_engineered 상태로 전이되지 않았습니다."
        assert "result" in result_data
        
        rev_res = result_data["result"]
        assert rev_res["is_passed"] is True, "역설계 로직이 성공(True) 상태를 반환해야 합니다."
        
        logger.info(f"[E2E In-Memory Test] 매칭 실패 후 역설계 파이프라인 안전 이행 검증 성공. 반환 결과: {result_data}")

@pytest.mark.anyio
@respx.mock
async def test_full_pipeline_e2e_invalid_smiles_error(in_memory_db):
    """
    E2E failure path test:
    When the 001 optimizer returns a recipe containing an invalid SMILES monomer,
    the orchestrator should catch the ValueError from monomer_mapper, log the failure,
    and return status 'error' with RDKit valence/parsing detail.
    """
    # 004 DB Mocking
    def db_search_handler(request):
        result = in_memory_db.query(Adherend).first()
        if result:
            return Response(200, json=[{
                "product_name": result.product_name,
                "classification": result.classification,
                "surface_energy_md": result.surface_energy_md,
                "roughness_md": result.roughness_md,
                "gloss_md": result.gloss_md,
                "thickness_mm": result.thickness_mm
            }])
        return Response(200, json=[])

    respx.get(url__regex=r"http://localhost:8004/adherends/search.*").mock(side_effect=db_search_handler)

    # Mock other services
    respx.post(url__regex=r"http://.*/analyze/image").mock(return_value=Response(200, json={"surface_energy": 45.0}))
    respx.post(url__regex=r"http://.*/analyze/roughness").mock(return_value=Response(200, json={"roughness": 0.15, "gloss": 150.0}))
    respx.post(url__regex=r"http://.*/api/v1/analyze").mock(return_value=Response(200, json={"metrics": {"estimated_radius_mm": 1.5}}))
    respx.post(url__regex=r"http://.*/calculate_processability").mock(
        return_value=Response(200, json={"level": 3, "is_fallback": False, "reason": "Mocked processing"})
    )
    respx.post(url__regex=r"http://.*/match").mock(
        return_value=Response(200, json={"recommendations": [], "is_successful": False})
    )

    # 001 returns a recipe with UNKNOWN monomer to trigger mapping error
    respx.post(url__regex=r"http://.*/optimize").mock(
        return_value=Response(200, json={"recipe": {"UNKNOWN_MONOMER": 0.5}, "predicted_properties": {"측정_값": 4800.0}})
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        db_res = httpx.get("http://localhost:8004/adherends/search?roughness_md_max=1.0")
        target_adherend = db_res.json()[0]

        payload = {
            "substrate_id": target_adherend["product_name"],
            "substrate_series": "SGV",
            "thickness_um": 100.0,
            "finish_type": target_adherend["classification"],
            "metrics": {
                "surface_energy": target_adherend["surface_energy_md"],
                "roughness": target_adherend["roughness_md"],
                "gloss": target_adherend["gloss_md"],
                "curvature_radius": 1.0
            },
            "target": {
                "target_initial_adhesion": 5000.0,
                "target_aged_adhesion": 5500.0,
                "target_tg": -20.0,
                "target_viscosity": 3500.0
            },
            "normal_vector_data": [0.01, 0.02, 0.01],
            "material_stiffness": 180.0
        }

        orch_res = await client.post("/orchestrate", json=payload)
        assert orch_res.status_code == 200
        result_data = orch_res.json()

        assert result_data["status"] == "error"
        assert result_data["error"] == "Module Execution Failed"
        assert "Monomer mapping not found for abbreviation" in result_data["details"]
