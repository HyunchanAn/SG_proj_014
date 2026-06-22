import pytest
import httpx
import logging

logger = logging.getLogger(__name__)

# 각 모듈별 포트 정의
MODULE_URLS = {
    "004_Database": "http://localhost:8004",
    "011_Processability": "http://localhost:8011",
    "012_Matching": "http://localhost:8012",
    "013_ReverseEngineering": "http://localhost:8013",
    "014_Orchestrator": "http://localhost:8014"
}

@pytest.mark.anyio
async def test_module_health_checks():
    """각 독립 모듈의 API 서버가 켜져 있고 통신이 가능한지 헬스체크를 수행합니다.
    Mock을 전혀 사용하지 않고 실제 포트로 통신하며, 서버가 꺼져 있으면 에러가 발생합니다.
    """
    async with httpx.AsyncClient() as client:
        for module_name, url in MODULE_URLS.items():
            try:
                # Swagger docs 또는 기본 루트 경로로 헬스체크 시도
                response = await client.get(f"{url}/docs", timeout=3.0)
                assert response.status_code == 200, f"{module_name}가 작동 중이나 docs 조회 실패 (Status: {response.status_code})"
                print(f"[OK] {module_name} ({url}) 가동 확인 완료.")
            except httpx.ConnectError:
                pytest.fail(f"[FAIL] {module_name} ({url}) 서버가 켜져 있지 않습니다. 가동 환경을 확인해 주세요.")
            except Exception as e:
                pytest.fail(f"[FAIL] {module_name} ({url}) 헬스체크 중 예외 발생: {str(e)}")

@pytest.mark.anyio
async def test_full_pipeline_e2e():
    """004 DB 모듈에서 피착재 정보를 조회한 뒤, 이를 바탕으로 014 오케스트레이터 파이프라인을 실행합니다.
    004 -> 011 -> 012 -> 013(매칭 실패 시) 전체 흐름이 실제 서버 연동으로 동작하는지 검증합니다.
    """
    db_url = MODULE_URLS["004_Database"]
    orchestrator_url = MODULE_URLS["014_Orchestrator"]

    # 1. 004 데이터베이스 모듈에서 조도 기준 피착재 탐색
    async with httpx.AsyncClient() as client:
        try:
            # 004 API 호출
            db_res = await client.get(f"{db_url}/adherends/search?roughness_md_max=1.0", timeout=5.0)
            assert db_res.status_code == 200, f"004 DB 조회 실패: {db_res.status_code}"
            adherends = db_res.json()
            assert len(adherends) > 0, "004 DB에 조건에 맞는 피착재 데이터가 존재하지 않습니다."
            
            # 첫 번째 피착재 선택
            target_adherend = adherends[0]
            print(f"[E2E] 선택된 피착재 데이터: {target_adherend}")
            
        except httpx.ConnectError:
            pytest.fail("004 Database API 서버에 연결할 수 없습니다.")
        except Exception as e:
            pytest.fail(f"004 DB 데이터 획득 중 오류 발생: {e}")

        # 2. 014 오케스트레이터 API 요청 페이로드 조립
        # schemas.OrchestrationRequest 형식에 맞춘다.
        payload = {
            "substrate_id": target_adherend.get("product_name") or target_adherend.get("classification") or "Unknown-Substrate",
            "surface_energy": target_adherend.get("surface_energy_md") or 35.0,
            "roughness": target_adherend.get("roughness_md") or 0.8,
            "finish_type": target_adherend.get("classification") or "Hairline",
            "normal_vector_data": [0.01, 0.02, 0.01],
            "curvature_radius": 2.5,
            "material_stiffness": 180.0
        }

        # 3. 014 오케스트레이터 호출
        try:
            orch_res = await client.post(f"{orchestrator_url}/orchestrate", json=payload, timeout=10.0)
            assert orch_res.status_code == 200, f"014 오케스트레이터 호출 실패: {orch_res.status_code}"
            
            result_data = orch_res.json()
            print(f"[E2E] 오케스트레이터 파이프라인 결과: {result_data}")
            
            # 워크플로우 성공 검증
            assert "status" in result_data, "오케스트레이터 반환 결과에 status 필드가 없습니다."
            assert result_data["status"] in ["matched", "reverse_engineered"], f"올바르지 않은 워크플로우 상태: {result_data['status']}"
            
            # 만약 matched 인 경우
            if result_data["status"] == "matched":
                assert "result" in result_data
                assert "recommendations" in result_data["result"]
                print(f"[E2E] 매칭 성공! 추천 제품: {result_data['result']['recommendations']}")
            
            # 만약 reverse_engineered 인 경우
            elif result_data["status"] == "reverse_engineered":
                assert "result" in result_data
                assert "predicted_properties" in result_data["result"]
                print(f"[E2E] 역설계 가동 완료. 예측 물성: {result_data['result']['predicted_properties']}")

        except httpx.ConnectError:
            pytest.fail("014 Orchestrator 서버에 연결할 수 없습니다.")
        except Exception as e:
            pytest.fail(f"오케스트레이터 파이프라인 가동 중 오류 발생: {e}")
