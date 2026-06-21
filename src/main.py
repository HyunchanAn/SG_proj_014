from fastapi import FastAPI
from src.schemas import OrchestrationRequest
from src.orchestrator import orchestrate_workflow
import uvicorn

app = FastAPI(title="SG_proj_014 Central Orchestrator", version="0.1.0")

@app.post("/orchestrate")
async def orchestrate(req: OrchestrationRequest):
    result = await orchestrate_workflow(req)
    return result

if __name__ == "__main__":
    uvicorn.run("src.main:app", host="0.0.0.0", port=8014, reload=True)
