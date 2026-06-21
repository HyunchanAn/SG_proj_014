import logging
import os
import httpx
from src.schemas import (
    OrchestrationRequest, ProcessabilityResult, MatchingResponse, VerificationResult
)

logger = logging.getLogger(__name__)

MODULE_011_URL = os.getenv("MODULE_011_URL", "http://localhost:8011")
MODULE_012_URL = os.getenv("MODULE_012_URL", "http://localhost:8012")
MODULE_013_URL = os.getenv("MODULE_013_URL", "http://localhost:8013")

async def call_module_011_processability(req: OrchestrationRequest) -> ProcessabilityResult:
    logger.info(f"Calling module 011 at {MODULE_011_URL}")
    payload = {
        "normal_vector_data": req.normal_vector_data,
        "curvature_radius": req.curvature_radius,
        "material_stiffness": req.material_stiffness
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.post(f"{MODULE_011_URL}/calculate_processability", json=payload)
            if res.status_code != 200:
                logger.error(f"Module 011 returned status {res.status_code}")
                return ProcessabilityResult(level=3, is_fallback=True, reason=f"Status {res.status_code}")
            return ProcessabilityResult(**res.json())
    except Exception as e:
        logger.error(f"Module 011 error: {e}")
        return ProcessabilityResult(level=3, is_fallback=True, reason=str(e))

async def call_module_012_matching(req: OrchestrationRequest, proc_level: int) -> MatchingResponse:
    logger.info(f"Calling module 012 at {MODULE_012_URL}")
    payload = {
        "substrate_id": req.substrate_id,
        "surface_energy": req.surface_energy,
        "roughness": req.roughness,
        "finish_type": req.finish_type,
        "required_processability_level": proc_level
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.post(f"{MODULE_012_URL}/match", json=payload)
            if res.status_code != 200:
                logger.error(f"Module 012 returned status {res.status_code}")
                return MatchingResponse(recommendations=[], is_successful=False)
            return MatchingResponse(**res.json())
    except Exception as e:
        logger.error(f"Module 012 error: {e}")
        return MatchingResponse(recommendations=[], is_successful=False)

async def call_module_013_reverse_engineering(req: OrchestrationRequest) -> VerificationResult:
    logger.info(f"Calling module 013 at {MODULE_013_URL}")
    payload = {
        "target_properties": {"adhesion": 10.0, "viscosity": 100.0},
        "xgboost_prediction": {"adhesion": 8.0, "viscosity": 90.0},
        "ir_gnn_features": [0.1, 0.2, 0.3],
        "current_iteration": 1
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.post(f"{MODULE_013_URL}/verify", json=payload)
            if res.status_code != 200:
                logger.error(f"Module 013 returned status {res.status_code}")
                return VerificationResult(is_passed=False, predicted_properties={}, error_rates={}, confidence_score=0.0)
            return VerificationResult(**res.json())
    except Exception as e:
        logger.error(f"Module 013 error: {e}")
        return VerificationResult(is_passed=False, predicted_properties={}, error_rates={}, confidence_score=0.0)

async def orchestrate_workflow(req: OrchestrationRequest):
    # Step 1: Processability (011)
    proc_result = await call_module_011_processability(req)
    
    # Step 2: Matching (012)
    match_result = await call_module_012_matching(req, proc_result.level)
    
    # Step 3: Reverse Engineering (013) if matching fails
    if not match_result.is_successful:
        rev_result = await call_module_013_reverse_engineering(req)
        return {"status": "reverse_engineered", "result": rev_result}
    
    return {"status": "matched", "result": match_result}

