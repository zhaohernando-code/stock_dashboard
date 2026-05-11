from __future__ import annotations

import importlib
import multiprocessing
import os
import sys
import traceback
from multiprocessing.connection import wait
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


def _akshare_worker(
    connection: Any,
    *,
    module_name: str,
    function_name: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    timeout_seconds: int,
    disable_proxies: bool,
) -> None:
    if disable_proxies:
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            os.environ.pop(key, None)

    patched_requests = _requests_request_with_default_timeout(timeout_seconds)
    try:
        module = importlib.import_module(module_name)
        function = getattr(module, function_name)
        connection.send(("ok", function(*args, **kwargs)))
    except Exception as exc:
        connection.send(
            (
                "error",
                {
                    "type": type(exc).__name__,
                    "message": str(exc),
                    "traceback": traceback.format_exc(limit=8),
                },
            )
        )
    finally:
        if patched_requests is not None:
            requests, original_request = patched_requests
            requests.sessions.Session.request = original_request
        connection.close()


def _multiprocessing_context() -> multiprocessing.context.BaseContext:
    try:
        ctx = multiprocessing.get_context("spawn")
    except ValueError:
        ctx = multiprocessing.get_context()

    executable = Path(sys.base_exec_prefix) / "bin" / f"python{sys.version_info.major}.{sys.version_info.minor}"
    if executable.exists():
        ctx.set_executable(str(executable))
    return ctx


def call_module_function_with_timeout(
    module_name: str,
    function_name: str,
    *,
    args: tuple[Any, ...] = (),
    kwargs: dict[str, Any] | None = None,
    timeout_seconds: int,
    disable_proxies: bool = False,
) -> Any:
    ctx = _multiprocessing_context()
    parent_connection, child_connection = ctx.Pipe(duplex=False)
    process = ctx.Process(
        target=_akshare_worker,
        kwargs={
            "connection": child_connection,
            "module_name": module_name,
            "function_name": function_name,
            "args": args,
            "kwargs": kwargs or {},
            "timeout_seconds": timeout_seconds,
            "disable_proxies": disable_proxies,
        },
    )
    process.start()
    child_connection.close()
    try:
        ready = wait([parent_connection, process.sentinel], timeout_seconds)
        if parent_connection not in ready:
            process.terminate()
            process.join(timeout=1)
            if process.is_alive():
                process.kill()
                process.join(timeout=1)
            raise AkshareCallTimeoutError(f"{module_name}.{function_name} timed out after {timeout_seconds}s")

        status, payload = parent_connection.recv()
        process.join(timeout=1)
        if status == "ok":
            return payload

        message = payload.get("message") or payload.get("type") or "unknown error"
        error_message = f"{module_name}.{function_name} failed: {message}"
        if payload.get("type") == "TypeError":
            raise TypeError(error_message)
        raise RuntimeError(error_message)
    finally:
        parent_connection.close()
        if process.is_alive():
            process.terminate()
            process.join(timeout=1)


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
