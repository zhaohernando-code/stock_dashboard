from __future__ import annotations

import subprocess
import shlex
from pathlib import Path

from pydantic import BaseModel

from ashare_evidence import artifact_store_core


ROOT = Path(__file__).resolve().parents[1]


class TinyArtifact(BaseModel):
    artifact_id: str
    status: str


def test_generated_artifacts_are_not_tracked_by_git() -> None:
    result = subprocess.run(
        ["git", "ls-files", "data/artifacts", "artifacts"],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )

    assert result.stdout.strip() == ""


def test_runtime_artifact_defaults_do_not_target_source_artifact_dirs() -> None:
    assert "data/artifacts/" in (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "data/runtime-artifacts/" in (ROOT / ".gitignore").read_text(encoding="utf-8")

    core_source = (ROOT / "src/ashare_evidence/artifact_store_core.py").read_text(encoding="utf-8")
    assert artifact_store_core.DEFAULT_ARTIFACT_ROOT == ROOT / "data" / "runtime-artifacts"
    assert 'project_root / "data" / "artifacts"' in core_source

    for script_name in ["run-scheduled-refresh.sh", "start-local-backend.sh"]:
        script = (ROOT / "scripts" / script_name).read_text(encoding="utf-8")
        assert 'ashare_resolve_local_artifact_root "$REPO_ROOT"' in script
        assert 'ASHARE_ARTIFACT_ROOT:-$REPO_ROOT/data/artifacts' not in script


def test_artifact_root_helper_rejects_legacy_source_paths() -> None:
    helper = ROOT / "scripts/ashare-artifact-root.sh"
    result = subprocess.run(
        [
            "bash",
            "-c",
            (
                f"source {shlex.quote(str(helper))}; "
                f"ASHARE_ARTIFACT_ROOT={shlex.quote(str(ROOT / 'data/artifacts'))} "
                f"ashare_resolve_local_artifact_root {shlex.quote(str(ROOT))}"
            ),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert result.returncode != 0
    assert "Refusing to use generated artifact root inside source checkout" in result.stderr


def test_default_artifact_reads_fall_back_to_legacy_source_artifact_root(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "data" / "runtime-artifacts"
    legacy_root = tmp_path / "data" / "artifacts"
    monkeypatch.setattr(artifact_store_core, "DEFAULT_ARTIFACT_ROOT", runtime_root)
    target = legacy_root / "shortpick_lab" / "legacy-fixture.json"
    target.parent.mkdir(parents=True)
    target.write_text('{"artifact_id": "legacy-fixture", "status": "readable"}\n', encoding="utf-8")

    artifact = artifact_store_core._read_model(
        TinyArtifact,
        "shortpick_lab",
        "legacy-fixture",
        default_artifact_root=runtime_root,
        project_root=tmp_path,
    )

    assert artifact.status == "readable"
