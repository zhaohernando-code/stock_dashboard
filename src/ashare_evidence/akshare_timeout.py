from __future__ import annotations

import importlib
import os
import pickle
import socket
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Any


class AkshareCallTimeoutError(TimeoutError):
    pass


def _requests_request_with_default_timeout(timeout_seconds: int):
    try:
        import requests
    except Exception:
        return None

    original_request = requests.sessions.Session.request

    def _request_with_timeout(self, method, url, **kwargs):
        kwargs.setdefault("timeout", timeout_seconds)
        return original_request(self, method, url, **kwargs)

    requests.sessions.Session.request = _request_with_timeout
    return requests, original_request


def _run_module_function(
    *,
    module_name: str,
    function_name: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    timeout_seconds: int,
    disable_proxies: bool,
) -> tuple[str, Any]:
    if disable_proxies:
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            os.environ.pop(key, None)

    previous_socket_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout_seconds)
    patched_requests = _requests_request_with_default_timeout(timeout_seconds)
    try:
        module = importlib.import_module(module_name)
        function = getattr(module, function_name)
        return "ok", function(*args, **kwargs)
    except Exception as exc:
        return (
            "error",
            {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(limit=8),
            },
        )
    finally:
        if patched_requests is not None:
            requests, original_request = patched_requests
            requests.sessions.Session.request = original_request
        socket.setdefaulttimeout(previous_socket_timeout)


def _worker_entry(input_path: str, output_path: str) -> int:
    with open(input_path, "rb") as handle:
        payload = pickle.load(handle)
    status, result = _run_module_function(**payload)
    with open(output_path, "wb") as handle:
        pickle.dump((status, result), handle, protocol=pickle.HIGHEST_PROTOCOL)
    return 0


def _python_executable() -> str:
    executable = Path(sys.base_exec_prefix) / "bin" / f"python{sys.version_info.major}.{sys.version_info.minor}"
    if executable.exists():
        return str(executable)
    return sys.executable


def call_module_function_with_timeout(
    module_name: str,
    function_name: str,
    *,
    args: tuple[Any, ...] = (),
    kwargs: dict[str, Any] | None = None,
    timeout_seconds: int,
    disable_proxies: bool = False,
) -> Any:
    with tempfile.TemporaryDirectory(prefix="akshare-call-") as temp_dir:
        temp_root = Path(temp_dir)
        input_path = temp_root / "input.pkl"
        output_path = temp_root / "output.pkl"
        with open(input_path, "wb") as handle:
            pickle.dump(
                {
                    "module_name": module_name,
                    "function_name": function_name,
                    "args": args,
                    "kwargs": kwargs or {},
                    "timeout_seconds": timeout_seconds,
                    "disable_proxies": disable_proxies,
                },
                handle,
                protocol=pickle.HIGHEST_PROTOCOL,
            )
        process = subprocess.Popen(
            [
                _python_executable(),
                "-m",
                "ashare_evidence.akshare_timeout",
                str(input_path),
                str(output_path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        try:
            process.wait(timeout=timeout_seconds + 2)
        except subprocess.TimeoutExpired as exc:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)
            raise AkshareCallTimeoutError(f"{module_name}.{function_name} timed out after {timeout_seconds}s") from exc

        if process.returncode != 0 or not output_path.exists():
            raise RuntimeError(f"{module_name}.{function_name} worker failed with exit code {process.returncode}")

        with open(output_path, "rb") as handle:
            status, payload = pickle.load(handle)
        if status == "ok":
            return payload

        message = payload.get("message") or payload.get("type") or "unknown error"
        error_message = f"{module_name}.{function_name} failed: {message}"
        if payload.get("type") == "TypeError":
            raise TypeError(error_message)
        raise RuntimeError(error_message)


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: python -m ashare_evidence.akshare_timeout INPUT.pkl OUTPUT.pkl")
    return _worker_entry(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    raise SystemExit(main())


def call_akshare_function(
    function_name: str,
    *,
    args: tuple[Any, ...] = (),
    kwargs: dict[str, Any] | None = None,
    timeout_seconds: int,
    disable_proxies: bool = False,
) -> Any:
    return call_module_function_with_timeout(
        "akshare",
        function_name,
        args=args,
        kwargs=kwargs,
        timeout_seconds=timeout_seconds,
        disable_proxies=disable_proxies,
    )
