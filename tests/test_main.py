import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from src.main import app
from src.schemas import ProcessabilityResult, MatchingResponse, VerificationResult

client = TestClient(app)

@pytest.mark.anyio
@patch("src.orchestrator.call_module_011_processability")
@patch("src.orchestrator.call_module_012_matching")
async def test_orchestrate_matched(mock_matching, mock_processability):
    # Mock Step 1 & 2
    mock_processability.return_value = ProcessabilityResult(
        level=2, is_fallback=False, reason="Test reason"
    )
    mock_matching.return_value = MatchingResponse(
        recommendations=[{"product_code": "PRD-001", "match_score": 85.0, "match_reason": {}}],
        is_successful=True
    )
    
    payload = {
        "substrate_id": "sub-001",
        "surface_energy": 35.0,
        "roughness": 0.8,
        "finish_type": "Hairline",
        "normal_vector_data": [0.1, 0.2],
        "curvature_radius": 10.0,
        "material_stiffness": 100.0
    }
    
    response = client.post("/orchestrate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "matched"
    assert data["result"]["is_successful"] is True

@pytest.mark.anyio
@patch("src.orchestrator.call_module_011_processability")
@patch("src.orchestrator.call_module_012_matching")
@patch("src.orchestrator.call_module_013_reverse_engineering")
async def test_orchestrate_reverse_engineered(mock_rev, mock_matching, mock_processability):
    # Mock Step 1, 2 (fails), 3 (succeeds)
    mock_processability.return_value = ProcessabilityResult(
        level=4, is_fallback=False, reason="Hard material"
    )
    mock_matching.return_value = MatchingResponse(
        recommendations=[],
        is_successful=False
    )
    mock_rev.return_value = VerificationResult(
        is_passed=True,
        predicted_properties={"adhesion": 9.5},
        error_rates={"adhesion": 0.05},
        confidence_score=0.95
    )
    
    payload = {
        "substrate_id": "sub-001",
        "surface_energy": 35.0,
        "roughness": 0.8,
        "finish_type": "Hairline",
        "normal_vector_data": [0.1, 0.2],
        "curvature_radius": 10.0,
        "material_stiffness": 100.0
    }
    
    response = client.post("/orchestrate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "reverse_engineered"
    assert data["result"]["is_passed"] is True
