from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "prune-runtime-output.sh"


def test_runtime_output_prune_keeps_recent_releases_and_removes_reconstructible_paths(tmp_path: Path) -> None:
    release_root = tmp_path / "output" / "releases"
    release_root.mkdir(parents=True)
    for index in range(4):
        release = release_root / f"release-{index}"
        release.mkdir()
        (release / "manifest.json").write_text("{}\n", encoding="utf-8")
        timestamp = 1000 + index
        os.utime(release, (timestamp, timestamp))
        local_manifest = release_root / f"local-{index}.json"
        local_manifest.write_text("{}\n", encoding="utf-8")
        os.utime(local_manifest, (timestamp, timestamp))
    (release_root / "latest-successful.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "frontend" / "node_modules").mkdir(parents=True)
    (tmp_path / "output" / "chrome-acceptance-profile").mkdir()
    (tmp_path / "output" / "playwright").mkdir()

    subprocess.run(
        ["bash", str(SCRIPT_PATH)],
        check=True,
        env={
            **os.environ,
            "ASHARE_RUNTIME_ROOT": str(tmp_path),
            "ASHARE_RUNTIME_RELEASE_KEEP_RECENT": "2",
        },
    )

    assert sorted(path.name for path in release_root.iterdir()) == [
        "latest-successful.json",
        "local-2.json",
        "local-3.json",
        "release-2",
        "release-3",
    ]
    assert not (tmp_path / "frontend" / "node_modules").exists()
    assert not (tmp_path / "output" / "chrome-acceptance-profile").exists()
    assert not (tmp_path / "output" / "playwright").exists()


def test_runtime_output_prune_dry_run_does_not_remove_paths(tmp_path: Path) -> None:
    release_root = tmp_path / "output" / "releases"
    for index in range(2):
        release = release_root / f"release-{index}"
        release.mkdir(parents=True)
        os.utime(release, (1000 + index, 1000 + index))

    subprocess.run(
        ["bash", str(SCRIPT_PATH)],
        check=True,
        env={
            **os.environ,
            "ASHARE_RUNTIME_ROOT": str(tmp_path),
            "ASHARE_RUNTIME_RELEASE_KEEP_RECENT": "1",
            "ASHARE_RUNTIME_OUTPUT_PRUNE_DRY_RUN": "1",
        },
    )

    assert len(list(release_root.iterdir())) == 2
