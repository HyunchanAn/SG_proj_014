import os
import httpx
from loguru import logger
from src.schemas import (
    OrchestrationRequest, ProcessabilityResult, MatchingResponse, VerificationResult
)

import asyncio
from src.config import config

# Core monomer to SMILES mapping for SG_proj_009 integration
MONOMER_SMILES = {
    "BA": "CCCCOC(=O)C=C",
    "2-EHA": "CCCCC(CC)COC(=O)C=C",
    "EA": "CCOC(=O)C=C",
    "MMA": "CC(=C)C(=O)OC",
    "AA": "C=CC(=O)O",
    "2-HEMA": "CC(=C)C(=O)OCCO",
    "St": "C=CC1=CC=CC=C1",
    "VAc": "CC(=O)OC=C"
}

MODULE_011_URL = config.MODULE_011_URL
MODULE_012_URL = config.MODULE_012_URL
MODULE_013_URL = config.MODULE_013_URL
MODULE_002_URL = config.MODULE_002_URL
MODULE_003_URL = config.MODULE_003_URL
MODULE_007_URL = config.MODULE_007_URL
import base64
from pathlib import Path

async def call_vision_modules(finish_type: str = "Hairline") -> dict:
    logger.info(f"Calling vision modules 002, 003, 007 concurrently with actual sample images for finish_type: {finish_type}")
    
    # Map finish type to real corporate sample images
    sample_dir = Path("E:/Github/SG_proj_015")
    prefix = "HL"
    if finish_type in ["Mirror", "BA"]:
        prefix = "BA"
    elif finish_type in ["2B", "2D"]:
        prefix = "2B"
        
    sfe_path = sample_dir / f"{prefix}_water_verify_step1_coin.jpg"
    vsams_path = sample_dir / f"{prefix}_reflect_verify_finish.jpg"
    terra_path = sample_dir / f"{prefix}_3d_verify_depth.jpg"
    
    # Fallback to any available image if path mismatch
    if not sfe_path.exists():
        img_files = list(sample_dir.glob("*.jpg"))
        if img_files:
            sfe_path = img_files[0]
            vsams_path = img_files[0]
            terra_path = img_files[0]
            
    sfe_data = b""
    vsams_base64 = ""
    terra_data = b""
    
    try:
        if sfe_path.exists():
            with open(sfe_path, "rb") as f:
                sfe_data = f.read()
        if vsams_path.exists():
            with open(vsams_path, "rb") as f:
                vsams_base64 = base64.b64encode(f.read()).decode("utf-8")
        if terra_path.exists():
            with open(terra_path, "rb") as f:
                terra_data = f.read()
    except Exception as io_err:
        logger.error(f"Failed to read real sample images for vision modules: {io_err}")

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            sfe_file = (sfe_path.name, sfe_data, "image/jpeg") if sfe_data else ("dummy.jpg", b"dummy_content", "image/jpeg")
            vsams_payload = {"image_data": vsams_base64} if vsams_base64 else {"image_data": "base64..."}
            terra_file = (terra_path.name, terra_data, "image/jpeg") if terra_data else ("dummy.jpg", b"dummy_content", "image/jpeg")
            
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
                    
            return vision_metrics
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
    
    # Initial target properties based on request
    current_targets = {
        "측정_값": req.target.target_initial_adhesion, 
        "점도(cP)": req.target.target_viscosity,
        "Tg": req.target.target_tg
    }
    
    # Fixed context (mocked for this example)
    fixed_ctx = {
        "온도": 83,
        "반응시간": 5,
        "박리_각도": 90,
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
                components = []
                from rdkit import Chem
                for monomer, ratio in best_recipe.items():
                    smiles = MONOMER_SMILES.get(monomer, "C=CC(=O)O") # Fallback to Acrylic Acid
                    
                    # RDKit Chemical Validity Check for Reverse Engineering Results
                    mol = Chem.MolFromSmiles(smiles)
                    if mol is None:
                        logger.error(f"014 Orchestrator: Invalid SMILES detected for monomer {monomer}: {smiles}")
                        raise ValueError(f"Invalid chemical SMILES structure for monomer {monomer}: {smiles}")
                        
                    components.append({
                        "smiles": smiles,
                        "ratio": float(ratio),
                        "n": 10  # represent polymerized/cured state
                    })
                
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
                    ir_gnn_features = data_009.get("transmittance", [0.0, 0.0, 0.0]) # Pass predicted transmittance spectrum
                    
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
                    # Update target properties based on proportional feedback deviation
                    if result.feedback_signal:
                        logger.info(f"Feedback received: {result.feedback_signal}. Adjusting targets.")
                        
                        target_adhesion = req.target.target_initial_adhesion
                        predicted_adhesion = xgboost_prediction.get("측정_값", target_adhesion)
                        
                        # Adjust target using proportional delta (damping coefficient 0.5)
                        adhesion_delta = (target_adhesion - predicted_adhesion) * 0.5
                        adhesion_delta = max(-200.0, min(200.0, adhesion_delta))
                        current_targets["측정_값"] += adhesion_delta
                        
            except Exception as e:
                logger.error(f"AI Loop error: {e}")
                raise RuntimeError(f"Reverse Engineering Failed: {e}")
            
    return VerificationResult(is_passed=False, predicted_properties={}, error_rates={}, confidence_score=0.0, feedback_signal={"error": "Max iterations reached"})

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
            vision_data = await call_vision_modules(req.finish_type)
            
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
            match_result = await call_module_012_matching(req, proc_result.level)
            
            # Step 3: Reverse Engineering (013)
            rev_result = await call_module_013_reverse_engineering(req)
            
            if not match_result.is_successful:
                logger.info(f"[Task {task_id}] Matching failed. Falling back to Reverse Engineered status.")
                return {"status": "reverse_engineered", "result": rev_result}
            
            logger.info(f"[Task {task_id}] Orchestration successful.")
            return {
                "status": "matched", 
                "result": match_result,
                "reverse_engineered_result": rev_result
            }
        
        except asyncio.TimeoutError as te:
            logger.error(f"[Task {task_id} | PID {pid}] Operation timed out during orchestration: {str(te)}")
            return {"status": "error", "error": "Operation Timeout", "details": str(te)}
        
        except RuntimeError as re:
            logger.error(f"[Task {task_id} | PID {pid}] Remote module execution failed: {str(re)}")
            return {"status": "error", "error": "Module Execution Failed", "details": str(re)}
        
        except Exception as e:
            logger.exception(f"[Task {task_id} | PID {pid}] Unhandled system error during orchestration: {str(e)}")
            return {"status": "error", "error": "Internal System Error", "details": str(e)}
        
        finally:
            logger.info(f"[Task {task_id} | PID {pid}] Orchestration workflow execution finished.")

