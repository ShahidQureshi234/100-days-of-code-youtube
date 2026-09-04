#!/usr/bin/env python3
"""SmartConvertAI engine CLI -- JSON in, JSON out.

Designed to be spawned by the Next.js API routes (or any host):

    python3 process_scan.py --stage health
    python3 process_scan.py --stage detect  --input u.jpg --workdir /tmp/j1
    python3 process_scan.py --stage process --workdir /tmp/j1 \
        --mode bw --corners '[[0.1,0.1],[0.9,0.1],[0.9,0.9],[0.1,0.9]]'
    python3 process_scan.py --stage export --workdirs '["/tmp/j1","/tmp/j2"]' \
        --mode bw --out /tmp/j1/scan.pdf --title "My Scan"

Every stage prints a single JSON object on stdout.  On failure the process
exits non-zero, prints the human-readable error on stderr, and still emits
``{"ok": false, "error": ...}`` on stdout for machine consumption.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

# Allow running both as `python3 process_scan.py` (from python-engine/) and
# `python3 -m engine.process_scan`.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine.pipeline import (  # noqa: E402
    PipelineError,
    stage_detect,
    stage_export,
    stage_health,
    stage_process,
)
from engine.imaging import ImageLoadError  # noqa: E402
from engine.pdf_export import ExportError  # noqa: E402


def _parse_json_arg(value: Optional[str], expected_type: type, name: str) -> Any:
    """Parse a JSON-encoded CLI argument with a helpful error message."""
    if value is None:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise PipelineError(f"--{name} is not valid JSON: {exc}") from exc
    if not isinstance(parsed, expected_type) and not (expected_type is list and isinstance(parsed, list)):
        raise PipelineError(f"--{name} must be JSON {expected_type.__name__}")
    return parsed


def _json_default(value: Any) -> Any:
    """Coerce numpy scalars (float32/int64/...) into plain Python for JSON."""
    if hasattr(value, "item"):
        return value.item()
    return str(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="process_scan.py",
        description="SmartConvertAI document scanner engine (JSON CLI)",
    )
    parser.add_argument("--stage", required=True, choices=("health", "detect", "process", "export"))
    parser.add_argument("--input", help="upload path (detect stage)")
    parser.add_argument("--workdir", help="page workspace directory (detect/process stages)")
    parser.add_argument("--corners", help="normalized corner quad JSON [[x,y]x4] (process stage, optional)")
    parser.add_argument("--mode", default="bw", choices=("bw", "color"), help="scan mode (process/export)")
    parser.add_argument("--settings", default=None, help="JSON object of mode-specific tuning knobs")
    parser.add_argument("--dpi", type=int, default=300, help="output physical resolution (default 300)")
    parser.add_argument("--color-codec", default="jpeg", choices=("jpeg", "jp2"), help="color layer codec")
    parser.add_argument("--mrc", dest="mrc", action=argparse.BooleanOptionalAction, default=True,
                        help="use MRC text-mask layout for color export (default: on)")
    parser.add_argument("--workdirs", help="JSON array of page workspaces (export stage)")
    parser.add_argument("--out", help="output PDF path (export stage)")
    parser.add_argument("--title", default="SmartConvertAI Scan", help="PDF document title")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        if args.stage == "health":
            result: Dict[str, Any] = stage_health()

        elif args.stage == "detect":
            if not args.input or not args.workdir:
                raise PipelineError("--input and --workdir are required for the detect stage")
            result = stage_detect(args.input, args.workdir)

        elif args.stage == "process":
            if not args.workdir:
                raise PipelineError("--workdir is required for the process stage")
            corners = _parse_json_arg(args.corners, list, "corners")
            settings = _parse_json_arg(args.settings, dict, "settings") or {}
            result = stage_process(
                workdir=args.workdir,
                corners=corners,
                mode=args.mode,
                settings=settings,
                dpi=args.dpi,
                color_codec=args.color_codec,
            )

        else:  # export
            workdirs = _parse_json_arg(args.workdirs, list, "workdirs")
            if not workdirs or not args.out:
                raise PipelineError("--workdirs (JSON array) and --out are required for the export stage")
            result = stage_export(
                workdirs=workdirs,
                mode=args.mode,
                out_path=args.out,
                title=args.title,
                dpi=args.dpi,
                color_codec=args.color_codec,
                use_mrc=args.mrc,
            )

        json.dump(result, sys.stdout, default=_json_default)
        sys.stdout.write("\n")
        return 0

    except (PipelineError, ImageLoadError, ExportError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        json.dump({"ok": False, "stage": args.stage, "error": str(exc)}, sys.stdout)
        sys.stdout.write("\n")
        return 2
    except Exception as exc:  # noqa: BLE001 - last-resort guard for the host
        traceback.print_exc(file=sys.stderr)
        json.dump({"ok": False, "stage": args.stage, "error": f"internal engine error: {exc}"}, sys.stdout)
        sys.stdout.write("\n")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
