from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class AgentState:
    problem: str
    max_attempts: int = 3
    attempt: int = 0
    code: str = ""
    explanation: str = ""
    stdout: str = ""
    stderr: str = ""
    success: bool = False
    error_history: List[str] = field(default_factory=list)
    diagnosis: Optional[str] = None
    from_memory: bool = False
    memory_context: Optional[str] = None

    def record_attempt(self, code: str, stdout: str, stderr: str, success: bool):
        self.code = code
        self.stdout = stdout
        self.stderr = stderr
        self.success = success
        
        if not success and stderr:
            self.error_history.append(stderr)
            
        self.attempt += 1
