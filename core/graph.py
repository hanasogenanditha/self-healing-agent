"""
LangGraph orchestration for the self-healing loop.

Three nodes: generate -> execute -> (analyze -> generate | end)

GenerationError and SandboxError are infra-level failures and are NOT
caught inside nodes — they propagate up to api/main.py as hard failures.
"""

from langgraph.graph import StateGraph, END

from core.state import AgentState
from core.sandbox import run_code, SandboxError
from agents.code_generator import generate, analyze_error, GenerationError
from memory.vector_store import find_similar_solution, store_solution, MemoryStoreError


def check_memory_node(state: AgentState) -> AgentState:
    try:
        match = find_similar_solution(state.problem)
    except MemoryStoreError as e:
        print(f"[memory] lookup failed, continuing without memory: {e}")
        return state

    print(f"[check_memory] match={'yes, sim=' + f'{match.similarity:.3f}' if match else 'no'}")

    if match:
        state.from_memory = True
        state.memory_context = (
            f"Problem: {match.problem}\nSolution:\n{match.code}\nExplanation: {match.explanation}"
        )
    return state


def generate_node(state: AgentState) -> AgentState:
    if state.attempt == 0:
        result = generate(problem=state.problem, memory_context=state.memory_context)
    else:
        result = generate(
            problem=state.problem,
            previous_code=state.code,
            error=state.stderr,
            diagnosis=state.diagnosis,
            attempt_number=state.attempt + 1,
        )
    state.code = result.code
    state.explanation = result.explanation
    return state


def execute_node(state: AgentState) -> AgentState:
    stdout, stderr, success = run_code(state.code)
    state.record_attempt(code=state.code, stdout=stdout, stderr=stderr, success=success)
    return state


def analyze_node(state: AgentState) -> AgentState:
    diagnosis = analyze_error(problem=state.problem, code=state.code, error=state.stderr)
    state.diagnosis = f"{diagnosis.error_type}: {diagnosis.root_cause}"
    return state


def store_memory_node(state: AgentState) -> AgentState:
    try:
        store_solution(problem=state.problem, code=state.code, explanation=state.explanation)
    except MemoryStoreError as e:
        print(f"[memory] store failed, continuing: {e}")
    return state


def should_continue(state: AgentState) -> str:
    if state.success:
        return "store"
    if state.attempt >= state.max_attempts:
        return "end"
    return "analyze"


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("check_memory", check_memory_node)
    graph.add_node("generate", generate_node)
    graph.add_node("execute", execute_node)
    graph.add_node("analyze", analyze_node)
    graph.add_node("store", store_memory_node)

    graph.set_entry_point("check_memory")
    graph.add_edge("check_memory", "generate")
    graph.add_edge("generate", "execute")
    graph.add_edge("analyze", "generate")
    graph.add_edge("store", END)

    graph.add_conditional_edges(
        "execute",
        should_continue,
        {"store": "store", "analyze": "analyze", "end": END},
    )

    return graph.compile()


compiled_graph = build_graph()