"""
Sandboxed Execution Engine.

Runs LLM-generated code inside an isolated, disposable Docker container.
No network access, no host filesystem access, capped resources, hard timeout.
"""

import os
import tempfile
import uuid
import io
import tarfile

import docker
from docker.errors import DockerException, ImageNotFound

import time
from core.metrics import SANDBOX_EXECUTION_TIME, SANDBOX_FAILURES

_IMAGE = "python:3.11-slim"
_TIMEOUT_SECONDS = 10
_MEM_LIMIT = "256m"
_NANO_CPUS = 500_000_000  # 0.5 of one CPU core


class SandboxError(Exception):
    """Raised for infrastructure problems (Docker unavailable, etc.) —
    distinct from the generated code itself failing to run."""
    pass


def _get_docker_client():
    try:
        return docker.from_env()
    except DockerException as e:
        raise SandboxError(f"Could not connect to Docker. Is Docker Desktop running? ({e})") from e


def _build_tar_with_code(code: str) -> bytes:
    """Builds an in-memory tar archive containing gen_code.py, for put_archive()."""
    code_bytes = code.encode("utf-8")
    tar_stream = io.BytesIO()
    with tarfile.open(fileobj=tar_stream, mode="w") as tar:
        info = tarfile.TarInfo(name="gen_code.py")
        info.size = len(code_bytes)
        tar.addfile(info, io.BytesIO(code_bytes))
    tar_stream.seek(0)
    return tar_stream.read()


def run_code(code: str) -> tuple[str, str, bool]:
    if not code or not code.strip():
        raise SandboxError("No code provided to execute.")

    start_time = time.monotonic()
    client = _get_docker_client()

    try:
        client.images.get(_IMAGE)
    except ImageNotFound:
        try:
            client.images.pull(_IMAGE)
        except DockerException as e:
            raise SandboxError(f"Could not pull Docker image '{_IMAGE}': {e}") from e

    container = None
    stdout = ""
    stderr = ""
    success = False

    try:
        container = client.containers.create(
            image=_IMAGE,
            command=["python", "/sandbox/gen_code.py"],
            network_disabled=True,
            mem_limit=_MEM_LIMIT,
            nano_cpus=_NANO_CPUS,
            working_dir="/sandbox",
            detach=True,
        )

        tar_bytes = _build_tar_with_code(code)
        container.put_archive(path="/", data=_wrap_in_sandbox_dir(tar_bytes))
        container.start()

        try:
            result = container.wait(timeout=_TIMEOUT_SECONDS)
            exit_code = result.get("StatusCode", 1)
            timed_out = False
        except Exception:
            container.kill()
            exit_code = None
            timed_out = True

        stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
        stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")

        if timed_out:
            success = False
            stderr = stderr + "\n[Execution timed out after {}s]".format(_TIMEOUT_SECONDS)
            SANDBOX_FAILURES.labels(reason="timeout").inc()
        else:
            success = (exit_code == 0)
            if not success:
                SANDBOX_FAILURES.labels(reason="nonzero_exit").inc()

        return stdout, stderr, success

    except DockerException as e:
        SANDBOX_FAILURES.labels(reason="infra_error").inc()
        raise SandboxError(f"Docker execution failed: {e}") from e

    finally:
        SANDBOX_EXECUTION_TIME.observe(time.monotonic() - start_time)
        if container is not None:
            try:
                container.remove(force=True)
            except DockerException:
                pass


def _wrap_in_sandbox_dir(gen_code_tar_bytes: bytes) -> bytes:
    """
    Re-packages the gen_code.py tar so its path is /sandbox/gen_code.py
    instead of /gen_code.py, since put_archive(path="/") extracts relative
    to whatever prefix we give the entries.
    """
    inner = io.BytesIO(gen_code_tar_bytes)
    with tarfile.open(fileobj=inner, mode="r") as src:
        code_member = src.getmember("gen_code.py")
        code_data = src.extractfile(code_member).read()

    out_stream = io.BytesIO()
    with tarfile.open(fileobj=out_stream, mode="w") as out:
        info = tarfile.TarInfo(name="sandbox/gen_code.py")
        info.size = len(code_data)
        out.addfile(info, io.BytesIO(code_data))
    out_stream.seek(0)
    return out_stream.read()