"""
code_executor.py — Sandboxed Python execution tool for JOI2.0

Lets JOI actually run code it writes, capture stdout/stderr/exceptions,
and feed the result back into the model so it can self-correct instead
of just guessing whether code works.

Integration point: call `run_code_tool()` from your existing call-method
dispatcher (the same place you'd wire a "search_web" or "read_file" tool).
"""

import subprocess
import tempfile
import os
import sys
import resource
import signal
from dataclasses import dataclass


@dataclass
class ExecResult:
    success: bool
    stdout: str
    stderr: str
    returncode: int
    timed_out: bool


def _limit_resources(max_mem_mb: int = 256):
    """Applied inside the child process before exec (Linux/Pardus only)."""
    def limiter():
        resource.setrlimit(resource.RLIMIT_AS, (max_mem_mb * 1024 * 1024,) * 2)
        resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
    return limiter


def run_code_tool(code: str, timeout: int = 8, max_mem_mb: int = 256) -> ExecResult:
    """
    Run untrusted Python code in a subprocess with CPU/memory/time limits.

    NOT a full security sandbox (no seccomp/container) — good enough to stop
    infinite loops, runaway memory, and accidental damage from JOI's own
    generated code. Do not expose this to code from arbitrary strangers.
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        path = f.name

    try:
        proc = subprocess.run(
            [sys.executable, path],
            capture_output=True,
            text=True,
            timeout=timeout,
            preexec_fn=_limit_resources(max_mem_mb) if os.name == "posix" else None,
        )
        return ExecResult(
            success=proc.returncode == 0,
            stdout=proc.stdout[-4000:],
            stderr=proc.stderr[-4000:],
            returncode=proc.returncode,
            timed_out=False,
        )
    except subprocess.TimeoutExpired as e:
        return ExecResult(
            success=False,
            stdout=(e.stdout or ""),
            stderr=f"Execution timed out after {timeout}s",
            returncode=-1,
            timed_out=True,
        )
    finally:
        os.unlink(path)


def self_correct_loop(model_call_fn, task_prompt: str, max_attempts: int = 3) -> dict:
    """
    Ask the model for code, run it, and if it fails, feed the error back
    for another attempt. `model_call_fn(prompt: str) -> str` should be your
    existing Ollama call (e.g. wrapping JOI's Llama 3.0 or a coder model).

    Returns a dict with the final code, result, and attempt history.
    """
    history = []
    prompt = task_prompt

    for attempt in range(1, max_attempts + 1):
        raw = model_call_fn(prompt)
        code = _extract_code_block(raw)
        result = run_code_tool(code)
        history.append({"attempt": attempt, "code": code, "result": result})

        if result.success:
            return {"success": True, "code": code, "result": result, "history": history}

        prompt = (
            f"The following code failed:\n\n{code}\n\n"
            f"Error:\n{result.stderr}\n\n"
            f"Fix the code and return only the corrected version."
        )

    return {"success": False, "code": code, "result": result, "history": history}


def _extract_code_block(text: str) -> str:
    """Pull the first ```python ... ``` or ``` ... ``` block out of model output."""
    if "```" not in text:
        return text.strip()
    parts = text.split("```")
    for part in parts[1::2]:
        cleaned = part.strip()
        if cleaned.startswith("python"):
            cleaned = cleaned[len("python"):].strip()
        if cleaned:
            return cleaned
    return text.strip()


if __name__ == "__main__":
    # quick manual test
    result = run_code_tool("print('JOI code executor online')\nprint(2 + 2)")
    print(result)