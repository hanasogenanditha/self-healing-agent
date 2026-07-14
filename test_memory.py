from memory.vector_store import init_db, store_solution, find_similar_solution, list_recent_solutions, MemoryStoreError
print("\n--- Storing a solution ---")
store_solution(
    problem="write a function that checks if a number e",
    code="def is_prime(n):\n    return n > 1 and all(n % i for i in range(2, n))",
    explanation="Checks divisibility for all numbers below n.",
)
print("Stored.")

print("\n--- Searching for a similar problem ---")
match = find_similar_solution("write a function to test if a number is a prime number")
if match:
    print(f"MATCH FOUND (similarity={match.similarity:.3f})")
    print("Matched problem:", match.problem)
    print("Code:\n", match.code)
else:
    print("No match found above threshold.")

print("\n--- Searching for an unrelated problem ---")
no_match = find_similar_solution("write a function to reverse a linked list")
print("Match:", no_match)


# ---------------------------------------------------------------------
# Graph-level test: does memory_context actually reach generate(),
# and does from_memory come back correctly on a fresh problem vs a
# reworded one that should hit the entry we just stored above?
# ---------------------------------------------------------------------
print("\n--- Running through compiled_graph ---")
run_graph = True

if run_graph:
    from core.graph import compiled_graph
    from core.state import AgentState

    print("\n[graph] first call: reworded prime-check problem (should hit memory)")
    state1 = AgentState(problem="write a function to test if a number is a prime number")
    result1 = compiled_graph.invoke(state1)
    fm1 = result1["from_memory"] if isinstance(result1, dict) else result1.from_memory
    print("from_memory:", fm1, "-- expected True")

    print("\n[graph] second call: unrelated problem (should NOT hit memory)")
    state2 = AgentState(problem="write a function that flattens a nested list")
    result2 = compiled_graph.invoke(state2)
    fm2 = result2["from_memory"] if isinstance(result2, dict) else result2.from_memory
    print("from_memory:", fm2, "-- expected False")
else:
    print("Skipped.")


# ---------------------------------------------------------------------
# Soft-failure test: stop Postgres, confirm the memory functions raise
# MemoryStoreError (not something uglier), then restart and confirm
# they recover without restarting this process.
# ---------------------------------------------------------------------
print("\n--- Soft-failure test ---")
run_softfail = False

if run_softfail:
    try:
        find_similar_solution("this should fail softly since postgres is down")
        print("UNEXPECTED: no exception raised -- did you actually stop Postgres?")
    except MemoryStoreError as e:
        print("OK: find_similar_solution raised MemoryStoreError:", e)
    except Exception as e:
        print(f"UNEXPECTED exception type ({type(e).__name__}):", e)

    try:
        store_solution("dummy problem while db down", "print(1)", "dummy")
        print("UNEXPECTED: no exception raised -- did you actually stop Postgres?")
    except MemoryStoreError as e:
        print("OK: store_solution raised MemoryStoreError:", e)
    except Exception as e:
        print(f"UNEXPECTED exception type ({type(e).__name__}):", e)

    input("Restart Postgres now, then press Enter to check recovery...")
    try:
        recent = list_recent_solutions(limit=1)
        print("OK: reconnected fine after restart, no process restart needed. Rows:", len(recent))
    except MemoryStoreError as e:
        print("STILL FAILING after Postgres restart:", e)
else:
    print("Skipped.")