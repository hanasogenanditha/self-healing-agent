"""
FastAPI layer for the Self-Healing Code Agent.

The retry loop now lives in core/graph.py (LangGraph). This file just
builds the initial state, invokes the graph, and formats the response.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from core.state import AgentState
from core.graph import compiled_graph
from core.sandbox import SandboxError
from agents.code_generator import GenerationError
from memory.vector_store import init_db, MemoryStoreError

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


@app.post("/solve", response_model=SolveResponse)
def solve(request: SolveRequest):
    initial_state = AgentState(problem=request.problem)

    try:
        final_state = compiled_graph.invoke(initial_state)
    except GenerationError as e:
        raise HTTPException(status_code=502, detail=f"Code generation failed: {e}")
    except SandboxError as e:
        raise HTTPException(status_code=500, detail=f"Sandbox execution failed: {e}")

    return SolveResponse(
        code=final_state["code"],
        explanation=final_state.get("explanation", ""),
        iterations=final_state["attempt"],
        errors_encountered=final_state["error_history"],
        from_memory=final_state.get("from_memory", False),
    )