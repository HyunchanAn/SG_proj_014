import sys
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from loguru import logger

from src.schemas import OrchestrationRequest
from src.orchestrator import orchestrate_workflow
import uvicorn

# Loguru Logger 설정 (JSON 및 표준 스트림 포맷 일치)
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO"
)
# 에러 로그는 파일에도 상시 적재되도록 회전 로깅 탑재
logger.add(
    "logs/orchestrator_{time:YYYY-MM-DD}.log",
    rotation="10 MB",
    retention="10 days",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
    level="WARNING"
)

app = FastAPI(title="SG_proj_014 Central Orchestrator", version="0.1.0")

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Pydantic ValidationError 및 FastAPI 요청 검증 에러 전역 캐칭 및 도메인 정밀 메시지 포맷 변환"""
    error_details = []
    for err in exc.errors():
        loc = " -> ".join(str(x) for x in err.get("loc", []))
        msg = err.get("msg", "유효성 검증 에러")
        error_details.append({"location": loc, "message": msg})
    
    log_msg = f"API Validation Error on {request.url.path}: {error_details}"
    logger.warning(log_msg)
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error_code": "DOMAIN_VALIDATION_FAILED",
            "detail": "표면 계측 물리값 또는 목표 수지 배합 임계조건이 어긋났습니다.",
            "validation_errors": error_details
        }
    )

@app.post(
    "/orchestrate",
    summary="E2E 모듈 오케스트레이션 (Step 1 -> Step 2 -> Step 3)",
    description="""
    Step 1의 계측 데이터(SFE, 조도, 곡률 등)와 Step 3의 타겟 데이터(점착력, Tg 등)를 한 번에 받아,
    011(가공성), 012(매칭), 013(역설계) 백엔드 모듈을 차례대로 호출하여 최종 결과를 반환합니다.
    - SFE 범위를 벗어나거나 Tg가 유효하지 않은 경우 422 에러와 함께 도메인 예외 메시지를 반환합니다.
    """,
    responses={
        200: {
            "description": "정상적으로 매칭 혹은 역설계가 수행됨",
        },
        422: {
            "description": "화학/물리 도메인 검증 실패 (Validation Error)",
        }
    }
)
async def orchestrate(req: OrchestrationRequest):
    logger.info(f"Orchestration request received for substrate: {req.substrate_id}")
    result = await orchestrate_workflow(req)
    logger.info(f"Orchestration completed successfully for substrate: {req.substrate_id}")
    return result

if __name__ == "__main__":
    uvicorn.run("src.main:app", host="0.0.0.0", port=8024, reload=True)
