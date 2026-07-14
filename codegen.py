from agents.code_generator import generate, analyze_error

print("--- Test 1: first attempt ---")
result = generate("write a function that checks if a number is prime")
print("CODE:\n", result.code)
print("\nEXPLANATION:\n", result.explanation)

# Simulate this code failing when run in the sandbox
broken_code = """
def is_prime(num):
    if n < 2:
        return False
    for i in range(2, n):
        if n % i == 0:
            return False
    return True

print(is_prime(7))
"""
error = "NameError: name 'n' is not defined. Did you mean: 'num'?"

print("\n--- Attempt 2 triggered: running error analysis first ---")
diagnosis = analyze_error(
    problem="write a function that checks if a number is prime",
    code=broken_code,
    error=error,
)
print("ERROR_TYPE:", diagnosis.error_type)
print("ROOT_CAUSE:", diagnosis.root_cause)

print("\n--- Now fixing using that diagnosis ---")
diagnosis_text = f"{diagnosis.error_type}: {diagnosis.root_cause}"

result = generate(
    problem="write a function that checks if a number is prime",
    previous_code=broken_code,
    error=error,
    diagnosis=diagnosis_text,
    attempt_number=2,
)
print("CODE:\n", result.code)
print("\nEXPLANATION:\n", result.explanation)