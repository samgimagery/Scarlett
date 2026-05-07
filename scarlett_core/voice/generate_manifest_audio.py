#!/usr/bin/env python3
"""Generate Scarlett voice assets from an approved manifest."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tts  # noqa: E402


def wav_duration_ms(path: Path) -> int | None:
    try:
        with wave.open(str(path), "rb") as w:
            frames = w.getnframes()
            rate = w.getframerate()
            if rate:
                return int(round(frames / rate * 1000))
    except Exception:
        return None
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="scarlett_core/voice/manifests/ams_first_recording_batch_v1.json")
    ap.add_argument("--assets-root", default="scarlett_core/voice/assets")
    ap.add_argument("--report", default="scarlett_core/voice/manifests/ams_first_recording_batch_v1_generation_report.json")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--skip-existing", action="store_true")
    args = ap.parse_args()

    manifest_path = Path(args.manifest)
    assets_root = Path(args.assets_root)
    report_path = Path(args.report)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    lines = manifest.get("lines", [])
    if args.limit:
        lines = lines[: args.limit]

    assets_root.mkdir(parents=True, exist_ok=True)
    rows = []
    ok_count = 0
    start_all = time.time()
    for idx, line in enumerate(lines, 1):
        dest = assets_root / line["asset_id"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "sequence": line.get("sequence"),
            "line_id": line.get("line_id"),
            "case_id": line.get("case_id"),
            "intent": line.get("intent"),
            "asset_id": line.get("asset_id"),
            "asset_path": str(dest),
            "text_fr_ca": line.get("text_fr_ca"),
            "target_speed": line.get("target_speed", 0.75),
        }
        print(f"[{idx}/{len(lines)}] {line['case_id']} {line['intent']} -> {dest}", flush=True)
        if args.skip_existing and dest.exists() and dest.stat().st_size > 1000:
            row.update({"ok": True, "skipped_existing": True, "bytes": dest.stat().st_size, "duration_ms": wav_duration_ms(dest)})
            ok_count += 1
            rows.append(row)
            continue
        t0 = time.time()
        try:
            generated = tts.generate_voice(line["text_fr_ca"], lang="fr", speed=float(line.get("target_speed", 0.75)))
            row["elapsed_sec"] = round(time.time() - t0, 3)
            if not generated:
                row.update({"ok": False, "error": "tts.generate_voice returned None"})
            else:
                generated_path = Path(generated)
                shutil.copy2(generated_path, dest)
                row.update({"ok": True, "source_path": str(generated_path), "bytes": dest.stat().st_size, "duration_ms": wav_duration_ms(dest)})
                ok_count += 1
        except Exception as exc:
            row.update({"ok": False, "elapsed_sec": round(time.time() - t0, 3), "error": repr(exc)})
        rows.append(row)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps({
            "ok": ok_count == len(lines),
            "completed": len(rows),
            "total": len(lines),
            "ok_count": ok_count,
            "elapsed_sec": round(time.time() - start_all, 3),
            "rows": rows,
        }, indent=2, ensure_ascii=False), encoding="utf-8")

    final = {
        "ok": ok_count == len(lines),
        "completed": len(rows),
        "total": len(lines),
        "ok_count": ok_count,
        "elapsed_sec": round(time.time() - start_all, 3),
        "assets_root": str(assets_root),
        "manifest": str(manifest_path),
        "rows": rows,
    }
    report_path.write_text(json.dumps(final, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: final[k] for k in ("ok", "completed", "total", "ok_count", "elapsed_sec", "assets_root")}, indent=2), flush=True)
    return 0 if final["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
