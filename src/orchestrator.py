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
MODULE_002_URL = os.getenv("MODULE_002_URL", "http://localhost:8002")
MODULE_003_URL = os.getenv("MODULE_003_URL", "http://localhost:8003")
MODULE_007_URL = os.getenv("MODULE_007_URL", "http://localhost:8007")
import asyncio
async def call_vision_modules(req: OrchestrationRequest):
    logger.info("Calling vision modules 002, 003, 007 concurrently")
    # This expects an image payload or path, simulating with concurrent requests
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            results = await asyncio.gather(
                client.post(f"{MODULE_002_URL}/analyze/sfe", json={"image_data": "base64..."}),
                client.post(f"{MODULE_003_URL}/analyze/roughness", json={"image_data": "base64..."}),
                client.post(f"{MODULE_007_URL}/analyze/curvature", json={"image_data": "base64..."}),
                return_exceptions=True
            )
            logger.info(f"Vision modules result: {results}")
        except Exception as e:
            logger.error(f"Vision modules error: {e}")
            raise RuntimeError(f"Vision module error: {e}")

async def call_module_011_processability(req: OrchestrationRequest) -> ProcessabilityResult:
    logger.info(f"Calling module 011 at {MODULE_011_URL}")
    payload = {
        "normal_vector_data": req.normal_vector_data,
        "curvature_radius": req.metrics.curvature_radius,
        "material_stiffness": req.material_stiffness
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.post(f"{MODULE_011_URL}/calculate_processability", json=payload)
            if res.status_code != 200:
                logger.error(f"Module 011 returned status {res.status_code}")
                raise RuntimeError(f"Module 011 Error: {res.status_code}")
            return ProcessabilityResult(**res.json())
    except Exception as e:
        logger.error(f"Module 011 error: {e}")
        raise RuntimeError(f"Module 011 communication failed: {e}")

async def call_module_012_matching(req: OrchestrationRequest, proc_level: int) -> MatchingResponse:
    logger.info(f"Calling module 012 at {MODULE_012_URL}")
    
    # Soft correction layer for BA vs Mirror misclassification based on physical crossover
    finish_type = req.finish_type
    if req.metrics.surface_energy >= 40.0 and req.metrics.gloss >= 450.0 and finish_type == "Mirror":
        logger.info("Software correction: Saturation detected on bright annealed surface. Mapping Mirror to BA.")
        finish_type = "BA"

    payload = {
        "substrate_id": req.substrate_id,
        "surface_energy": req.metrics.surface_energy,
        "roughness": req.metrics.roughness,
        "finish_type": finish_type,
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
    logger.info(f"Starting reverse engineering loop with {MODULE_013_URL}")
    MAX_ITERATIONS = 5
    current_adhesion, current_viscosity = 0.0, 0.0
    ir_gnn_features = [0.0, 0.0, 0.0]
    
    for iteration in range(1, MAX_ITERATIONS + 1):
        logger.info(f"Iteration {iteration}/{MAX_ITERATIONS}")
        payload = {
            "target_properties": {
                "adhesion": req.target.target_adhesion, 
                "viscosity": req.target.target_viscosity,
                "tg": req.target.target_tg
            },
            "xgboost_prediction": {"adhesion": current_adhesion, "viscosity": current_viscosity},
            "ir_gnn_features": ir_gnn_features,
            "current_iteration": iteration
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(f"{MODULE_013_URL}/verify", json=payload)
                if res.status_code != 200:
                    logger.error(f"Module 013 returned status {res.status_code}")
                    break
                
                result = VerificationResult(**res.json())
                if result.is_passed:
                    logger.info("Reverse engineering loop converged successfully.")
                    return result
                else:
                    # Update parameters from feedback signal for next iteration
                    # (Dummy logic here assumes the signal provides updated properties)
                    if result.feedback_signal:
                        current_adhesion += 1.0
                        current_viscosity += 2.0
                        ir_gnn_features = [x + 0.1 for x in ir_gnn_features]
        except Exception as e:
            logger.error(f"Module 013 error: {e}")
            raise RuntimeError(f"Reverse Engineering Failed: {e}")
            
    return VerificationResult(is_passed=False, predicted_properties={}, error_rates={}, confidence_score=0.0, feedback_signal="Max iterations reached")

def apply_physical_corrections(req: OrchestrationRequest) -> OrchestrationRequest:
    # 1. HL 이방성 표면의 SFE Cassie-Baxter/Wenzel 왜곡 보정 레이어
    # 조도(Ra)와 마감 종류가 Hairline인 경우, apparent SFE를 실제 열역학적 수치로 보상
    if req.finish_type == "Hairline" and req.metrics.roughness > 0.0:
        alpha = 0.65  # HL 연마 채널 보정 계수
        original_sfe = req.metrics.surface_energy
        # SFE 보정식: SFE_corrected = SFE_measured * (1 + alpha * Ra)
        corrected_sfe = original_sfe * (1.0 + alpha * req.metrics.roughness)
        corrected_sfe = min(45.0, corrected_sfe)
        logger.info(f"Physical correction applied on HL surface: SFE corrected from {original_sfe:.2f} to {corrected_sfe:.2f}")
        req.metrics.surface_energy = corrected_sfe
    return req

async def orchestrate_workflow(req: OrchestrationRequest):
    # Apply physical and visual soft correction rules before processing
    req = apply_physical_corrections(req)

    # Step 0: Vision Modules (002, 003, 007)
    await call_vision_modules(req)

    # Step 1: Processability (011)
    proc_result = await call_module_011_processability(req)
    
    # Step 2: Matching (012)
    match_result = await call_module_012_matching(req, proc_result.level)
    
    # Step 3: Reverse Engineering (013) - Always run for cross-comparison & recipe analysis
    rev_result = await call_module_013_reverse_engineering(req)
    
    if not match_result.is_successful:
        return {"status": "reverse_engineered", "result": rev_result}
    
    # Return both matched product and reverse engineered formula if successful
    return {
        "status": "matched", 
        "result": match_result,
        "reverse_engineered_result": rev_result
    }



