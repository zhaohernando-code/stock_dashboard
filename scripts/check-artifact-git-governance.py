#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ARTIFACT_ROOTS = {
    ROOT / "artifacts",
    ROOT / "data" / "artifacts",
}
HARDCODED_PATH_ALLOWLIST = {
    Path("scripts/ashare-artifact-root.sh"),
    Path("scripts/check-artifact-git-governance.py"),
    Path("scripts/publish-local-runtime.sh"),
    Path("tests/test_artifact_git_governance.py"),
    Path("tests/test_publish_script_static.py"),
}


def fail(message: str) -> None:
    print(f"artifact-git-governance blocked: {message}", file=sys.stderr)
    raise SystemExit(1)


def require_text(path: str, needle: str) -> None:
    content = (ROOT / path).read_text(encoding="utf-8")
    if needle not in content:
        fail(f"{path} missing required text: {needle}")


def forbid_text(path: str, needle: str) -> None:
    content = (ROOT / path).read_text(encoding="utf-8")
    if needle in content:
        fail(f"{path} contains forbidden stale text: {needle}")


def tracked(paths: list[str]) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", *paths],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def require_default_artifact_root() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from ashare_evidence.artifact_store_core import DEFAULT_ARTIFACT_ROOT

    expected = ROOT / "data" / "runtime-artifacts"
    if DEFAULT_ARTIFACT_ROOT.resolve() != expected.resolve():
        fail(f"DEFAULT_ARTIFACT_ROOT must resolve to {expected}, got {DEFAULT_ARTIFACT_ROOT}")
    resolved_default = DEFAULT_ARTIFACT_ROOT.resolve()
    for source_root in SOURCE_ARTIFACT_ROOTS:
        try:
            resolved_default.relative_to(source_root.resolve())
        except ValueError:
            continue
        fail(f"DEFAULT_ARTIFACT_ROOT still points inside generated source artifact root: {resolved_default}")


def require_no_unapproved_hardcoded_source_artifact_paths() -> None:
    scan_roots = [ROOT / "src", ROOT / "scripts", ROOT / "tests", ROOT / ".github"]
    offenders: list[str] = []
    for scan_root in scan_roots:
        if not scan_root.exists():
            continue
        for path in scan_root.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(ROOT)
            if relative in HARDCODED_PATH_ALLOWLIST:
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if "data/artifacts" in content:
                offenders.append(str(relative))

    if offenders:
        fail("unapproved hardcoded source artifact path references:\n" + "\n".join(offenders[:20]))


def main() -> int:
    tracked_generated = tracked(["data/artifacts", "artifacts"])
    if tracked_generated:
        preview = "\n".join(tracked_generated[:20])
        fail(f"generated artifacts are still tracked:\n{preview}")

    for entry in [
        "data/artifacts/",
        "data/runtime-artifacts/",
        "artifacts/",
        "data/*.db-*",
        "data/*.sqlite-*",
    ]:
        require_text(".gitignore", entry)

    require_default_artifact_root()
    require_no_unapproved_hardcoded_source_artifact_paths()
    require_text("src/ashare_evidence/artifact_store_core.py", 'project_root / "data" / "artifacts"')

    for script in ["scripts/run-scheduled-refresh.sh", "scripts/start-local-backend.sh"]:
        require_text(script, 'source "$ARTIFACT_ROOT_HELPER"')
        require_text(script, 'ashare_resolve_local_artifact_root "$REPO_ROOT"')
        forbid_text(script, 'ASHARE_ARTIFACT_ROOT:-$REPO_ROOT/data/artifacts')

    require_text("scripts/publish-local-runtime.sh", 'ASHARE_ARTIFACT_ROOT:-$RUNTIME_ROOT/data/artifacts')

    require_text("scripts/ashare-artifact-root.sh", "ashare_reject_source_artifact_root")
    require_text("scripts/ashare-artifact-root.sh", "ASHARE_ALLOW_REPO_ARTIFACT_WRITES")
    print("artifact-git-governance: pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
