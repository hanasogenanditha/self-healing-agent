from core.sandbox import run_code

print("--- Test 1: simple success ---")
stdout, stderr, success = run_code("print('hello world')")
print("stdout:", repr(stdout))
print("stderr:", repr(stderr))
print("success:", success)

print("\n--- Test 2: runtime error ---")
stdout, stderr, success = run_code("print(undefined_variable)")
print("stdout:", repr(stdout))
print("stderr:", repr(stderr))
print("success:", success)

print("\n--- Test 3: timeout ---")
stdout, stderr, success = run_code("import time; time.sleep(15)")
print("stdout:", repr(stdout))
print("stderr:", repr(stderr))
print("success:", success)