#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

def main() -> int:
    ap = argparse.ArgumentParser(description="Run MassGen against LM Studio via OpenAI-compatible env vars.")
    ap.add_argument("--config", required=True, help="Path to MassGen YAML config")
    ap.add_argument("--out", required=True, help="Output run directory")
    ap.add_argument("--prompt", required=True, help="User prompt/question")
    ap.add_argument("--base-url", default="http://127.0.0.1:1234/v1", help="LM Studio OpenAI-compatible base URL")
    ap.add_argument("--api-key", default="local", help="Dummy API key for local server")
    ap.add_argument("--orchestrator-timeout", type=int, default=240, help="MassGen orchestrator timeout seconds")
    args = ap.parse_args()

    out = Path(args.out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)

    stdout_path = out / "massgen_stdout.log"
    stderr_path = out / "massgen_stderr.log"
    inv_path = out / "massgen_invocation.json"

    massgen_bin = Path(sys.executable).resolve().parent / "massgen"
    cmd = [
        str(massgen_bin) if massgen_bin.exists() else "massgen",
        "--no-display",
        "--debug",
        "--orchestrator-timeout",
        str(args.orchestrator_timeout),
        "--config",
        str(Path(args.config).expanduser().resolve()),
        args.prompt,
    ]

    env = dict(os.environ)
    env["OPENAI_BASE_URL"] = args.base_url
    env["OPENAI_API_KEY"] = args.api_key

    t0 = time.time()
    with stdout_path.open("w", encoding="utf-8") as out_f, stderr_path.open("w", encoding="utf-8") as err_f:
        try:
            cp = subprocess.run(cmd, cwd=str(out), env=env, stdout=out_f, stderr=err_f, text=True)
            rc = int(cp.returncode)
        except Exception as e:
            rc = 2
            err_f.write(f"\n[LAUNCHER] Exception: {type(e).__name__}: {e}\n")

    inv = {
        "schema": "qct.massgen.lmstudio.launch.v1",
        "cmd": cmd,
        "cwd": str(out),
        "returncode": rc,
        "ok": (rc == 0),
        "wall_s": round(time.time() - t0, 3),
        "openai_base_url": args.base_url,
        "openai_api_key_set": bool(args.api_key),
    }
    inv_path.write_text(json.dumps(inv, indent=2) + "\n", encoding="utf-8")

    print(str(out))
    return rc

if __name__ == "__main__":
    raise SystemExit(main())
