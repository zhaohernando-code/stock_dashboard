from __future__ import annotations

import base64
import json
import os
import subprocess
from typing import Any
from urllib import request
from urllib.error import HTTPError, URLError

from ashare_evidence.http_client import urlopen

DEFAULT_CONTROL_PLANE_API_BASE = ""
DEFAULT_CONTROL_PLANE_REMOTE_API_BASE = "http://127.0.0.1:8787"
DEFAULT_CONTROL_PLANE_SSH_TARGET = "codex-server"


def control_plane_api_base() -> str:
    return (os.getenv("ASHARE_CONTROL_PLANE_API_BASE") or DEFAULT_CONTROL_PLANE_API_BASE).strip().rstrip("/")


def control_plane_remote_api_base() -> str:
    return (os.getenv("ASHARE_CONTROL_PLANE_REMOTE_API_BASE") or DEFAULT_CONTROL_PLANE_REMOTE_API_BASE).strip().rstrip("/")


def control_plane_ssh_target() -> str:
    return (os.getenv("ASHARE_CONTROL_PLANE_SSH_TARGET") or DEFAULT_CONTROL_PLANE_SSH_TARGET).strip()


def post_control_plane_task_via_ssh(
    payload: dict[str, Any],
    *,
    ssh_target: str | None = None,
    remote_api_base: str | None = None,
) -> dict[str, Any]:
    target = (ssh_target or control_plane_ssh_target()).strip()
    if not target:
        raise RuntimeError("Control-plane SSH relay target is empty.")
    remote_base = (remote_api_base or control_plane_remote_api_base()).strip().rstrip("/")
    if not remote_base:
        raise RuntimeError("Control-plane remote API base is empty.")
    endpoint = f"{remote_base}/api/tasks"
    encoded_payload = base64.b64encode(json.dumps(payload, ensure_ascii=False).encode("utf-8")).decode("ascii")
    remote_script = "\n".join(
        [
            "python3 - <<'PY'",
            "import base64",
            "import json",
            "import urllib.request",
            f"endpoint = {endpoint!r}",
            f"payload = base64.b64decode({encoded_payload!r})",
            "request_obj = urllib.request.Request(",
            "    endpoint,",
            "    data=payload,",
            "    headers={'Content-Type': 'application/json'},",
            "    method='POST',",
            ")",
            "with urllib.request.urlopen(request_obj, timeout=30) as response:",
            "    print(response.read().decode('utf-8'))",
            "PY",
        ]
    )
    try:
        completed = subprocess.run(
            ["ssh", target, remote_script],
            check=True,
            capture_output=True,
            text=True,
            timeout=45,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Control-plane SSH relay timed out after {exc.timeout}s.") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise RuntimeError(f"Control-plane SSH relay failed: {detail}") from exc
    try:
        return json.loads((completed.stdout or "").strip())
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Control-plane SSH relay returned invalid JSON: {(completed.stdout or '').strip()}") from exc


def control_plane_endpoint_label(*, api_base: str | None = None) -> str:
    explicit_base = (api_base or "").strip().rstrip("/")
    if explicit_base:
        return explicit_base
    return f"ssh://{control_plane_ssh_target()} -> {control_plane_remote_api_base()}"


def post_control_plane_task(payload: dict[str, Any], *, api_base: str | None = None) -> dict[str, Any]:
    base = (api_base or control_plane_api_base()).strip().rstrip("/")
    if not base:
        return post_control_plane_task_via_ssh(payload)
    endpoint = f"{base}/api/tasks"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    http_request = request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(http_request, timeout=30, disable_proxies=True) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore") or str(exc)
        raise RuntimeError(f"Control-plane task creation failed with HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Control-plane task creation failed: {exc.reason}") from exc
