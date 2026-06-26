from fastapi import FastAPI
from src.schemas import OrchestrationRequest
from src.orchestrator import orchestrate_workflow
import uvicorn

app = FastAPI(title="SG_proj_014 Central Orchestrator", version="0.1.0")

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
    result = await orchestrate_workflow(req)
    return result

if __name__ == "__main__":
    uvicorn.run("src.main:app", host="0.0.0.0", port=8014, reload=True)
