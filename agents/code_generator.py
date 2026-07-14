"""
Code Generation Agent + Error Analysis Agent.

generate() is used for both the first attempt and every retry.
analyze_error() is a separate call used only on retries, to diagnose
the failure before generate() attempts a fix.
"""

import os
import re
from dataclasses import dataclass
from typing import Optional

from google import genai
from dotenv import load_dotenv

load_dotenv()

_API_KEY = os.getenv("GEMINI_API_KEY")
if not _API_KEY:
    raise RuntimeError("GEMINI_API_KEY not found in environment. Check your .env file.")

_client = genai.Client(api_key=_API_KEY)
_MODEL = "gemini-2.5-flash"


class GenerationError(Exception):
    """Raised when the Gemini API call itself fails (network, auth, rate limit).
    Kept separate from code execution errors, which live in AgentState."""
    pass


@dataclass
class GenerationResult:
    code: str
    explanation: str
    raw_response: str


@dataclass
class DiagnosisResult:
    error_type: str
    root_cause: str
    raw_response: str


def _build_initial_prompt(problem: str, memory_context: Optional[str] = None) -> str:
    context_block = ""
    if memory_context:
        context_block = f"""
A similar problem was solved before — use it as a reference if it's genuinely
relevant, but adapt fully to the exact problem below rather than copying it:

{memory_context}
"""

    return f"""You are an expert Python developer. Write a Python function to solve this problem:

{problem}
{context_block}
Requirements:
- Return complete, runnable Python code.
- Include a small example call at the bottom that demonstrates the function working (so it produces visible output when run).
- Do not include explanations inside the code block itself.

Respond in exactly this format:

```python
<your code here>
```

EXPLANATION:
<2-3 sentence explanation of your approach>
"""


def _build_diagnosis_prompt(problem: str, code: str, error: str) -> str:
    return f"""You are debugging a Python function that failed to run.

Original problem:
{problem}

Code that failed:
```python
{code}
```

Error produced:
{error}

Diagnose this error. Do NOT write any code or fix anything yet — only diagnose.

Respond in exactly this format:

ERROR_TYPE: <syntax error | logic error | missing import | wrong variable name | type error | other>
ROOT_CAUSE: <1-2 sentence explanation of why this happened>
"""


def _build_fix_prompt(problem: str, previous_code: str, error: str, diagnosis: str, attempt_number: int) -> str:
    urgency = ""
    if attempt_number >= 3:
        urgency = (
            "\nThis code has failed multiple times. Slow down, re-read the error "
            "carefully line by line, and check variable names, types, and indentation "
            "before responding.\n"
        )

    return f"""You are fixing a Python function that failed to run.

Original problem:
{problem}

Previous code:
```python
{previous_code}
```

Error produced:
{error}

Diagnosis of the error:
{diagnosis}
{urgency}
Fix the code using this diagnosis. Keep the parts that were working; only change
what's necessary to fix the error.

Respond in exactly this format:

```python
<your fixed code here>
```

EXPLANATION:
<2-3 sentence explanation of what was wrong and what you changed>
"""


def _parse_response(raw_text: str) -> GenerationResult:
    code_match = re.search(r"```python\s*(.*?)```", raw_text, re.DOTALL)
    if not code_match:
        code_match = re.search(r"```\s*(.*?)```", raw_text, re.DOTALL)

    if not code_match:
        raise GenerationError(
            f"Could not find a code block in Gemini's response. Raw response:\n{raw_text}"
        )

    code = code_match.group(1).strip()

    explanation_match = re.search(r"EXPLANATION:\s*(.*)", raw_text, re.DOTALL)
    explanation = explanation_match.group(1).strip() if explanation_match else ""

    return GenerationResult(code=code, explanation=explanation, raw_response=raw_text)


def analyze_error(problem: str, code: str, error: str) -> DiagnosisResult:
    prompt = _build_diagnosis_prompt(problem, code, error)

    try:
        response = _client.models.generate_content(
            model=_MODEL,
            contents=prompt,
            config={
                "temperature": 0.1,
                "max_output_tokens": 512,
            },
        )
    except Exception as e:
        raise GenerationError(f"Gemini API call failed during error analysis: {e}") from e

    raw_text = response.text
    if not raw_text:
        raise GenerationError("Gemini returned an empty response during error analysis.")

    type_match = re.search(r"ERROR_TYPE:\s*(.*)", raw_text)
    cause_match = re.search(r"ROOT_CAUSE:\s*(.*)", raw_text, re.DOTALL)

    error_type = type_match.group(1).strip() if type_match else "unknown"
    root_cause = cause_match.group(1).strip() if cause_match else raw_text.strip()

    return DiagnosisResult(error_type=error_type, root_cause=root_cause, raw_response=raw_text)


def generate(
    problem: str,
    previous_code: Optional[str] = None,
    error: Optional[str] = None,
    diagnosis: Optional[str] = None,
    attempt_number: int = 1,
    memory_context: Optional[str] = None,
) -> GenerationResult:
    """
    Generate or fix Python code.

    First attempt:  generate(problem)
    Retry attempt:  generate(problem, previous_code=..., error=..., diagnosis=..., attempt_number=...)
    """
    is_retry = previous_code is not None and error is not None

    if is_retry:
        prompt = _build_fix_prompt(problem, previous_code, error, diagnosis or "", attempt_number)
    else:
        prompt = _build_initial_prompt(problem, memory_context=memory_context)

    try:
        response = _client.models.generate_content(
            model=_MODEL,
            contents=prompt,
            config={
                "temperature": 0.2,
                "max_output_tokens": 4096,
            },
        )
    except Exception as e:
        raise GenerationError(f"Gemini API call failed: {e}") from e

    raw_text = response.text
    if not raw_text:
        raise GenerationError("Gemini returned an empty response.")

    return _parse_response(raw_text)