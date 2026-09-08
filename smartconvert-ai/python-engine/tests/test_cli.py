"""End-to-end CLI contract tests (the exact interface Next.js relies on)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
CLI = ENGINE_ROOT / "process_scan.py"


def run_cli(*args: str) -> dict:
    proc = subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True,
        text=True,
        cwd=str(ENGINE_ROOT),
        timeout=180,
    )
    assert proc.returncode == 0, f"CLI failed ({proc.returncode}): {proc.stderr[-2000:]}"
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_health_stage():
    result = run_cli("--stage", "health")
    assert result["ok"] is True
    assert result["opencv"]
    assert result["img2pdf"]


def test_full_flow_bw(skewed_photo, tmp_path):
    workdir = tmp_path / "job"
    workdir.mkdir()

    detect = run_cli("--stage", "detect", "--input", str(skewed_photo), "--workdir", str(workdir))
    assert detect["ok"] and detect["cornersAuto"] is True
    assert len(detect["corners"]) == 4
    assert (workdir / detect["previewDetect"]).is_file()

    process = run_cli(
        "--stage", "process",
        "--workdir", str(workdir),
        "--mode", "bw",
        "--corners", json.dumps(detect["corners"]),
    )
    assert process["ok"]
    assert process["stats"]["processedBytes"] > 0
    assert process["stats"]["reductionPct"] > 50  # JPEG photo -> G4 tiff

    export = run_cli(
        "--stage", "export",
        "--workdirs", json.dumps([str(workdir)]),
        "--mode", "bw",
        "--out", str(tmp_path / "out.pdf"),
        "--title", "CLI Test Scan",
    )
    assert export["ok"] and export["pdfBytes"] > 0
    pdf = (tmp_path / "out.pdf").read_bytes()
    assert pdf[:5] == b"%PDF-"
    assert b"/CCITTFaxDecode" in pdf


def test_full_flow_color_mrc(skewed_photo, tmp_path):
    workdir = tmp_path / "job"
    workdir.mkdir()

    run_cli("--stage", "detect", "--input", str(skewed_photo), "--workdir", str(workdir))
    process = run_cli("--stage", "process", "--workdir", str(workdir), "--mode", "color")
    assert process["ok"]

    export = run_cli(
        "--stage", "export",
        "--workdirs", json.dumps([str(workdir)]),
        "--mode", "color",
        "--out", str(tmp_path / "color.pdf"),
        "--mrc",
    )
    assert export["strategy"] == "color-mrc"
    data = (tmp_path / "color.pdf").read_bytes()
    assert b"/ImageMask" in data


def test_error_contract(tmp_path):
    """Bad input must exit non-zero AND emit machine-readable JSON."""
    proc = subprocess.run(
        [sys.executable, str(CLI), "--stage", "detect", "--input", str(tmp_path / "missing.jpg"), "--workdir", str(tmp_path)],
        capture_output=True,
        text=True,
        cwd=str(ENGINE_ROOT),
        timeout=60,
    )
    assert proc.returncode != 0
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert payload["ok"] is False
    assert "error" in payload
