import time
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from core.state import AgentState
from core.graph import compiled_graph
from core.sandbox import SandboxError
from agents.code_generator import GenerationError
from memory.vector_store import init_db, MemoryStoreError
from core.metrics import REQUEST_LATENCY, RUN_SUCCESS, RUN_FAILURE

app = FastAPI(title="Self-Healing Code Agent")


@app.on_event("startup")
def on_startup():
    try:
        init_db()
    except MemoryStoreError as e:
        print(f"[memory] init_db failed at startup: {e}")


class SolveRequest(BaseModel):
    problem: str
    language: str = "python"


class SolveResponse(BaseModel):
    code: str
    explanation: str
    iterations: int
    errors_encountered: list[str]
    from_memory: bool = False


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/solve", response_model=SolveResponse)
def solve(request: SolveRequest):
    start_time = time.monotonic()
    initial_state = AgentState(problem=request.problem)

    try:
        final_state = compiled_graph.invoke(initial_state)
    except GenerationError as e:
        RUN_FAILURE.labels(reason="generation_error").inc()
        REQUEST_LATENCY.labels(endpoint="/solve").observe(time.monotonic() - start_time)
        raise HTTPException(status_code=502, detail=f"Code generation failed: {e}")
    except SandboxError as e:
        RUN_FAILURE.labels(reason="sandbox_error").inc()
        REQUEST_LATENCY.labels(endpoint="/solve").observe(time.monotonic() - start_time)
        raise HTTPException(status_code=500, detail=f"Sandbox execution failed: {e}")

    REQUEST_LATENCY.labels(endpoint="/solve").observe(time.monotonic() - start_time)

    if final_state.get("success"):
        RUN_SUCCESS.inc()
    else:
        RUN_FAILURE.labels(reason="max_attempts").inc()

    return SolveResponse(
        code=final_state["code"],
        explanation=final_state.get("explanation", ""),
        iterations=final_state["attempt"],
        errors_encountered=final_state["error_history"],
        from_memory=final_state.get("from_memory", False),
    )