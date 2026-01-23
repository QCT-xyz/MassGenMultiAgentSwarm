#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List

from massgen_ext.cohos import reasons
from massgen_ext.cohos.artifacts import init_bundle, write_decision, write_manifest_and_hashes, write_policy_copy


def _load_json(path: str) -> Dict[str, Any]:
    p = Path(path).expanduser().resolve()
    return json.loads(p.read_text(encoding="utf-8"))


def _find_coordination_table(run_dir: Path) -> Path | None:
    base = run_dir / ".massgen" / "massgen_logs"
    if not base.exists():
        return None
    for t in base.rglob("attempt_1/coordination_table.txt"):
        return t
    for t in base.rglob("coordination_table.txt"):
        return t
    return None


def _parse_restarts_total(coord_table: Path | None) -> int:
    if coord_table is None or (not coord_table.exists()):
        return 0
    txt = coord_table.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^\|\s*Restarts\s*\|(.+?)\|\s*$", txt, flags=re.MULTILINE)
    if not m:
        return 0
    cells = [c.strip() for c in m.group(1).split("|")]
    total = 0
    for c in cells:
        mm = re.search(r"(\d+)\s*restarts?", c)
        if mm:
            total += int(mm.group(1))
    return total


def main() -> int:
    ap = argparse.ArgumentParser(description="CohOS runner: invokes LM Studio launcher + emits CohOS artifacts.")
    ap.add_argument("--policy", required=True, help="Policy JSON path")
    ap.add_argument("--out", required=True, help="Run output directory")
    ap.add_argument("--prompt", required=True, help="Prompt")
    args = ap.parse_args()

    run_id = f"cohos-lmstudio-{uuid.uuid4().hex[:12]}"
    bundle = init_bundle(args.out)

    # refusal-first default
    decision = "REFUSE"
    reason = reasons.INTERNAL_ERROR_STEP_FAIL
    policy_id = "unknown"
    details: Dict[str, Any] = {"run_id": run_id}

    try:
        policy_obj = _load_json(args.policy)
        policy_id = str(policy_obj.get("policy_id") or "unknown")
        write_policy_copy(bundle, policy_obj)

        cfg_path = str(policy_obj.get("config_path") or "").strip()
        if not cfg_path:
            raise ValueError("policy missing required field: config_path")

        base_url = str(policy_obj.get("lmstudio_base_url") or "http://127.0.0.1:1234/v1")
        api_key = str(policy_obj.get("lmstudio_api_key") or "local")
        timeout_s = int(policy_obj.get("timeout_s") or 300)
        orchestrator_timeout = int(policy_obj.get("orchestrator_timeout_s") or 240)

        # D: thresholds for ALLOW/MARGINAL/REFUSE
        max_restarts_allow = int(policy_obj.get("max_restarts_allow", 2))
        max_restarts_refuse = int(policy_obj.get("max_restarts_refuse", 10))
        max_wall_s_allow = float(policy_obj.get("max_wall_s_allow", 420))
        max_wall_s_refuse = float(policy_obj.get("max_wall_s_refuse", 900))

        launcher = Path("scripts/run_massgen_lmstudio.py").resolve()
        if not launcher.exists():
            raise FileNotFoundError(f"launcher not found: {launcher}")

        cfg_abs = str(Path(cfg_path).expanduser().resolve())

        cmd: List[str] = [
            sys.executable,
            str(launcher),
            "--config", cfg_abs,
            "--out", str(bundle.run_dir),
            "--prompt", args.prompt,
            "--base-url", base_url,
            "--api-key", api_key,
            "--orchestrator-timeout", str(orchestrator_timeout),
        ]

        t0 = time.time()
        try:
            cp = subprocess.run(cmd, cwd=str(Path.cwd()), timeout=timeout_s)
            rc = int(cp.returncode)
            ok = (rc == 0)
            details.update({"launcher_rc": rc, "wall_s": round(time.time() - t0, 3)})
        except subprocess.TimeoutExpired:
            ok = False
            rc = 124
            details.update({"launcher_rc": rc, "wall_s": round(time.time() - t0, 3), "timeout_s": timeout_s})

        # Compute orchestration metrics (best-effort)
        coord_table = _find_coordination_table(bundle.run_dir)
        restarts_total = _parse_restarts_total(coord_table)

        details.update({
            "metrics": {
                "wall_s": details.get("wall_s"),
                "restarts_total": restarts_total,
                "coordination_table": str(coord_table) if coord_table else None
            },
            "thresholds": {
                "max_restarts_allow": max_restarts_allow,
                "max_restarts_refuse": max_restarts_refuse,
                "max_wall_s_allow": max_wall_s_allow,
                "max_wall_s_refuse": max_wall_s_refuse
            }
        })

        if not ok:
            decision = "REFUSE"
            reason = reasons.INTERNAL_ERROR_STEP_FAIL
        else:
            wall_s = float(details.get("wall_s") or 0.0)
            if (restarts_total > max_restarts_refuse) or (wall_s > max_wall_s_refuse):
                decision = "REFUSE"
                reason = reasons.COHERENCE_ENVELOPE_FAIL
            elif (restarts_total > max_restarts_allow) or (wall_s > max_wall_s_allow):
                decision = "MARGINAL"
                reason = reasons.COHERENCE_ENVELOPE_FAIL
            else:
                decision = "ALLOW"
                reason = reasons.ALLOW_ALL_CHECKS_PASS

        write_decision(bundle, decision=decision, reason=reason, policy_id=policy_id, run_id=run_id, details=details)

        extra: List[Path] = []
        for fp in [bundle.run_dir / "massgen_stdout.log", bundle.run_dir / "massgen_stderr.log", bundle.run_dir / "massgen_invocation.json"]:
            if fp.exists():
                extra.append(fp)

        # Include files under .massgen (not the directory itself)
        massgen_dir = bundle.run_dir / ".massgen"
        if massgen_dir.exists():
            for f in massgen_dir.rglob("*"):
                if f.is_file():
                    extra.append(f)

        write_manifest_and_hashes(bundle, extra_files=extra)
        print(str(bundle.run_dir))
        return 0 if decision in ("ALLOW", "MARGINAL") else 1

    except Exception as e:
        details.update({"error": f"{type(e).__name__}: {e}"})
        try:
            write_decision(bundle, decision="REFUSE", reason=reasons.INTERNAL_ERROR_STEP_FAIL, policy_id=policy_id, run_id=run_id, details=details)
            write_manifest_and_hashes(bundle)
        except Exception:
            pass
        print(str(bundle.run_dir))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
