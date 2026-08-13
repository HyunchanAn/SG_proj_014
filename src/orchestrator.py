import asyncio
import os

import httpx
from loguru import logger

from src.config import config
from src.schemas import (
    MatchingResponse,
    OrchestrationRequest,
    ProcessabilityResult,
    VerificationResult,
)
from src.utils import monomer_mapper

MODULE_011_URL = config.MODULE_011_URL
MODULE_012_URL = config.MODULE_012_URL
MODULE_013_URL = config.MODULE_013_URL
MODULE_002_URL = config.MODULE_002_URL
MODULE_003_URL = config.MODULE_003_URL
MODULE_007_URL = config.MODULE_007_URL
import base64
from pathlib import Path

class ModuleExecutionError(Exception):
    def __init__(self, module_id: str, code: str, message: str):
        self.module_id = module_id
        self.code = code
        self.message = message
        super().__init__(self.message)

async def call_vision_modules(finish_type: str = "Hairline", image_base64: str | None = None) -> tuple[dict, bool]:
    is_degraded = False
    if image_base64:
        logger.info(f"Calling vision modules concurrently with provided base64 image for finish_type: {finish_type}")
        # Decode base64 to bytes for file uploads
        try:
            image_data = base64.b64decode(image_base64)
        except Exception as e:
            logger.error(f"Failed to decode base64 image: {e}. Falling back to degraded mode.")
            image_data = b"dummy_content"
            is_degraded = True
    else:
        logger.warning("No image provided. Using degraded mode (dummy content) for vision modules.")
        image_base64 = "dummy_base64..."
        image_data = b"dummy_content"
        is_degraded = True

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            sfe_file = ("image.jpg", image_data, "image/jpeg")
            vsams_payload = {"image_data": image_base64}
            terra_file = ("image.jpg", image_data, "image/jpeg")
            
            results = await asyncio.gather(
                client.post(f"{MODULE_002_URL}/analyze/image", data={"volume_ul": 2.0, "ref_diameter_mm": 24.0}, files={"file": sfe_file}),
                client.post(f"{MODULE_003_URL}/analyze/roughness", json=vsams_payload),
                client.post(f"{MODULE_007_URL}/api/v1/analyze", data={"ref_length_mm": 100.0, "roughness": 1.0}, files={"file": terra_file}),
                return_exceptions=True
            )
            logger.info(f"Vision modules result: {results}")
            
            vision_metrics = {}
            # Extract results
            for res in results:
                if isinstance(res, httpx.Response) and res.status_code == 200:
                    data = res.json()
                    # 007 (SG-TERRA) returns curvature
                    if "metrics" in data and "estimated_radius_mm" in data["metrics"]:
                        vision_metrics["curvature_radius"] = data["metrics"]["estimated_radius_mm"]
                    # 003 (V-SAMS) returns roughness and gloss
                    if "roughness" in data:
                        vision_metrics["roughness"] = data["roughness"]
                    if "gloss" in data:
                        vision_metrics["gloss"] = data["gloss"]
                    
            return vision_metrics, is_degraded
        except Exception as e:
            logger.error(f"Vision modules error: {e}")
            raise ModuleExecutionError("vision", "VISION_ERROR", f"Vision module error: {e}")

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
                raise ModuleExecutionError("011", "PROC_ERROR", f"Module 011 Error: {res.status_code}")
            return ProcessabilityResult(**res.json())
    except Exception as e:
        logger.error(f"Module 011 error: {e}")
        if isinstance(e, ModuleExecutionError):
            raise e
        raise ModuleExecutionError("011", "PROC_COMM_ERROR", f"Module 011 communication failed: {e}")

async def call_module_012_matching(req: OrchestrationRequest, proc_level: int, task_id: str) -> MatchingResponse:
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
            headers = {"X-Request-ID": task_id}
            res = await client.post(f"{MODULE_012_URL}/match", json=payload, headers=headers)
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
    
    # Initial target properties based on request
    current_targets = {
        "측정_값": req.target.target_initial_adhesion, 
        "점도(cP)": req.target.target_viscosity,
        "Tg": req.target.target_tg
    }
    
    # Fixed context mapping for surrogate models (including newly required Adhesion test conditions)
    fixed_ctx = {
        "온도": 83,
        "반응시간": 5,
        "박리_각도": req.target.adhesion_test_angle,
        "점착_기재": req.target.adhesion_test_substrate,
        "금속_표면": req.finish_type
    }
    
    for iteration in range(1, MAX_ITERATIONS + 1):
        logger.info(f"Iteration {iteration}/{MAX_ITERATIONS}")
        
        xgboost_prediction = {}
        ir_gnn_features = []
        best_recipe = {}
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                # 1. Call 001 (PolySim) to optimize recipe
                logger.info(f"Calling 001 PolySim API: {config.MODULE_001_URL}/optimize")
                res_001 = await client.post(
                    f"{config.MODULE_001_URL}/optimize", 
                    json={"target_properties": current_targets, "fixed_context": fixed_ctx}
                )
                if res_001.status_code == 200:
                    data_001 = res_001.json()
                    best_recipe = data_001.get("recipe", {})
                    xgboost_prediction = data_001.get("predicted_properties", {})
                    
                # 2. Call 009 (IR GNN) to predict IR features based on the recipe
                logger.info(f"Calling 009 IR GNN API: {config.MODULE_009_URL}/predict")
                components = monomer_mapper.convert_recipe_to_components(best_recipe, config.N_POLYMERIZATION)
                
                res_009 = await client.post(
                    f"{config.MODULE_009_URL}/predict",
                    json={
                        "components": components,
                        "use_qc": False,
                        "solvent": "None"
                    }
                )
                if res_009.status_code == 200:
                    data_009 = res_009.json()
                    ir_gnn_features = monomer_mapper.extract_gnn_features(data_009)
                    
                # 2.5 Call 006 (TransPolymer GNN API) to predict open-dataset based Tg and blend with 001 lab-data
                logger.info(f"Calling 006 TransPolymer GNN API: {config.MODULE_006_URL}/predict")
                gnn_tg = 0.0
                total_ratio = 0.0
                for monomer, ratio in best_recipe.items():
                    smiles = monomer_mapper.MONOMER_SMILES_MAP.get(monomer)
                    if smiles:
                        try:
                            res_006 = await client.post(
                                f"{config.MODULE_006_URL}/predict",
                                json={"smiles": smiles},
                                timeout=5.0
                            )
                            if res_006.status_code == 200:
                                data_006 = res_006.json()
                                gnn_tg += data_006.get("Tg", -25.0) * (ratio / 100.0)
                                total_ratio += (ratio / 100.0)
                        except Exception as e_006:
                            logger.warning(f"006 GNN prediction failed for {monomer}: {e_006}")
                
                if total_ratio > 0:
                    gnn_tg = gnn_tg / total_ratio
                else:
                    gnn_tg = -25.0
                    
                if "Tg" in xgboost_prediction:
                    original_xgboost_tg = xgboost_prediction["Tg"]
                    # Blend 001 (Lab-data) and 006 (Open-dataset GNN) with a 50:50 ratio
                    xgboost_prediction["Tg"] = (original_xgboost_tg + gnn_tg) / 2.0
                    logger.info(f"Tg Blended: 001 Lab Tg ({original_xgboost_tg:.2f}) + 006 GNN Tg ({gnn_tg:.2f}) -> Blended Tg ({xgboost_prediction['Tg']:.2f})")

                    
                # 3. Call 013 (QA Gateway) to verify
                payload = {
                    "target_properties": {
                        "측정_값": req.target.target_initial_adhesion, 
                        "점도(cP)": req.target.target_viscosity,
                        "Tg": req.target.target_tg
                    },
                    "xgboost_prediction": xgboost_prediction,
                    "ir_gnn_features": ir_gnn_features,
                    "current_iteration": iteration
                }
                
                logger.info(f"Calling 013 QA Gateway API: {MODULE_013_URL}/verify")
                res_013 = await client.post(f"{MODULE_013_URL}/verify", json=payload)
                if res_013.status_code != 200:
                    logger.error(f"Module 013 returned status {res_013.status_code}")
                    break
                
                result = VerificationResult(**res_013.json())
                if result.is_passed:
                    logger.info("Reverse engineering loop converged successfully.")
                    result.predicted_properties["final_recipe"] = best_recipe
                    return result
                else:
                    # Apply explicit target adjustments proposed by QA Gateway (013)
                    if result.feedback_signal and "target_adjustments" in result.feedback_signal:
                        adjustments = result.feedback_signal["target_adjustments"]
                        logger.info(f"Applying target adjustments from 013: {adjustments}")
                        
                        for k, v in adjustments.items():
                            if k in current_targets:
                                current_targets[k] += v
                        
            except Exception as e:
                logger.error(f"AI Loop error: {e}")
                raise ModuleExecutionError("013", "REV_ENG_FAILED", f"Reverse Engineering Failed: {e}")
            
    # If we reached max iterations, return the last result anyway instead of empty dummy
    result.predicted_properties["final_recipe"] = best_recipe
    return result

def apply_physical_corrections(req: OrchestrationRequest) -> OrchestrationRequest:
    # 1. HL 이방성 표면의 SFE Cassie-Baxter/Wenzel 왜곡 보정 레이어
    # 조도(Ra)와 마감 종류가 Hairline인 경우, apparent SFE를 실제 열역학적 수치로 보상
    if req.finish_type == "Hairline" and req.metrics.roughness > 0.0:
        alpha = config.alpha  # HL 연마 채널 보정 계수 (config 파일 수치 반영)
        original_sfe = req.metrics.surface_energy
        # SFE 보정식: SFE_corrected = SFE_measured * (1 + alpha * Ra)
        corrected_sfe = original_sfe * (1.0 + alpha * req.metrics.roughness)
        corrected_sfe = min(45.0, corrected_sfe)
        logger.info(f"Physical correction applied on HL surface: SFE corrected from {original_sfe:.2f} to {corrected_sfe:.2f}")
        req.metrics.surface_energy = corrected_sfe
    return req

import uuid


async def orchestrate_workflow(req: OrchestrationRequest):
    task_id = str(uuid.uuid4())[:8]
    pid = os.getpid()
    # Using loguru contextual logging
    with logger.contextualize(task_id=task_id, pid=pid):
        logger.info(f"[Task {task_id} | PID {pid}] Starting orchestration workflow for {req.substrate_id} ({req.finish_type})")
        
        try:
            # Step 0: Vision Modules (002, 003, 007)
            vision_data, is_degraded = await call_vision_modules(req.finish_type, req.image_base64)
            
            if "curvature_radius" in vision_data:
                req.metrics.curvature_radius = vision_data["curvature_radius"]
            if "roughness" in vision_data:
                req.metrics.roughness = vision_data["roughness"]
            if "gloss" in vision_data:
                req.metrics.gloss = vision_data["gloss"]

            req = apply_physical_corrections(req)

            # Step 1: Processability (011)
            proc_result = await call_module_011_processability(req)
            
            # Apply substrate thickness penalty
            penalty_table = config.processability_thickness_penalty
            series_dict = penalty_table.get(req.substrate_series, {})
            penalty = series_dict.get(str(int(req.thickness_um)), 0)
            
            if penalty != 0:
                logger.info(f"[Task {task_id}] Applying thickness penalty {penalty} for {req.substrate_series} {req.thickness_um}um")
                proc_result.level = max(1, min(5, proc_result.level + penalty))
            
            # Step 2: Matching (012)
            match_result = await call_module_012_matching(req, proc_result.level, task_id)
            
            # Step 3: Reverse Engineering (013)
            rev_result = await call_module_013_reverse_engineering(req)
            
            if not match_result.is_successful:
                logger.info(f"[Task {task_id}] Matching failed. Falling back to Reverse Engineered status.")
                return {
                    "status": "reverse_engineered", 
                    "result": rev_result,
                    "processability": proc_result.dict()
                }
            
            logger.info(f"[Task {task_id}] Orchestration successful.")
            return {
                "status": "matched", 
                "result": match_result,
                "reverse_engineered_result": rev_result,
                "processability": proc_result.dict(),
                "degraded": is_degraded
            }

        
        except ModuleExecutionError as me:
            logger.error(f"[Task {task_id} | PID {pid}] Module execution failed: {me.module_id} - {me.message}")
            return {"status": "error", "error_code": me.code, "module": me.module_id, "message": me.message}
            
        except asyncio.TimeoutError as te:
            logger.error(f"[Task {task_id} | PID {pid}] Operation timed out during orchestration: {str(te)}")
            return {"status": "error", "error_code": "TIMEOUT", "module": "014", "message": f"Operation Timeout: {str(te)}"}
        
        except RuntimeError as re:
            logger.error(f"[Task {task_id} | PID {pid}] Remote module execution failed: {str(re)}")
            return {"status": "error", "error_code": "MODULE_EXECUTION_FAILED", "module": "014", "message": f"Remote module execution failed: {str(re)}"}
        
        except Exception as e:
            logger.exception(f"[Task {task_id} | PID {pid}] Unhandled system error during orchestration: {str(e)}")
            return {"status": "error", "error_code": "INTERNAL_ERROR", "module": "014", "message": f"Internal System Error: {str(e)}"}
        
        finally:
            logger.info(f"[Task {task_id} | PID {pid}] Orchestration workflow execution finished.")

