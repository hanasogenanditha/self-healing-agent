"""
Prometheus metrics for the self-healing agent.
"""

from prometheus_client import Counter, Histogram

# API-level
REQUEST_LATENCY = Histogram(
    "agent_request_latency_seconds",
    "Latency of API requests",
    ["endpoint"],
)

RUN_SUCCESS = Counter(
    "agent_run_success_total",
    "Number of /solve runs that ended successfully",
)

RUN_FAILURE = Counter(
    "agent_run_failure_total",
    "Number of /solve runs that ended in failure",
    ["reason"],  # "generation_error" | "sandbox_error" | "max_attempts"
)

# Graph/retry-level
RETRY_COUNT = Counter(
    "agent_retry_count_total",
    "Number of times the generate->execute loop retried after a failure",
)

MEMORY_HITS = Counter(
    "agent_memory_hits_total",
    "Number of times a similar problem was found in memory",
)

MEMORY_MISSES = Counter(
    "agent_memory_misses_total",
    "Number of times no similar problem was found in memory",
)

# Sandbox-level
SANDBOX_EXECUTION_TIME = Histogram(
    "agent_sandbox_execution_seconds",
    "Time spent executing generated code in the Docker sandbox",
)

SANDBOX_FAILURES = Counter(
    "agent_sandbox_failures_total",
    "Number of sandbox executions that failed",
    ["reason"],  # "timeout" | "nonzero_exit" | "infra_error"
)