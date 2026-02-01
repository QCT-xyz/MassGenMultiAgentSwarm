from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, List

from . import reasons
from .artifacts import init_bundle, write_decision, write_manifest_and_hashes, write_policy_copy


@dataclass(frozen=True)
class Policy:
    policy_id: str
    require_massgen_success: bool = True
    orchestrator_timeout_s: int = 600
    massgen_args: Optional[List[str]] = None
    # If true, wrapper refuses if API key env vars are present (prevents accidental live calls).
    forbid_live_keys: bool = False
    allow_live_keys: bool = False


def _load_json(path: str) -> Dict[str, Any]:
    p = Path(path).expanduser().resolve()
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def _parse_policy(policy_obj: Dict[str, Any]) -> Policy:
    policy_id = str(policy_obj.get("policy_id") or "").strip()
    if not policy_id:
        raise ValueError("policy_id missing or empty")

    require_massgen_success = bool(policy_obj.get("require_massgen_success", True))
    orchestrator_timeout_s = int(policy_obj.get("orchestrator_timeout_s", 600))

    massgen_args = policy_obj.get("massgen_args")
    if massgen_args is not None and not isinstance(massgen_args, list):
        raise ValueError("massgen_args must be a list of strings if provided")

    forbid_live_keys = bool(policy_obj.get("forbid_live_keys", False))
    allow_live_keys = bool(policy_obj.get("allow_live_keys", False))

    return Policy(
        policy_id=policy_id,
        require_massgen_success=require_massgen_success,
        orchestrator_timeout_s=orchestrator_timeout_s,
        massgen_args=massgen_args,
        forbid_live_keys=forbid_live_keys,
        allow_live_keys=allow_live_keys,
    )


def _env_sanitized(policy: Policy) -> Tuple[Dict[str, str], Dict[str, Any]]:
    """
    Do not record or pass provider secrets unless user explicitly wants that.
    Canon-default: strip known key vars from subprocess env to prevent accidental live calls.
    """
    base = dict(os.environ)

    secret_vars = [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "XAI_API_KEY",
        "ZAI_API_KEY",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_KEY",
    ]

    present = [k for k in secret_vars if base.get(k)]
    if policy.forbid_live_keys and present:
        raise RuntimeError(f"Live key env vars present but forbidden by policy: {present}")

    stripped = []
    passed = []
    if policy.allow_live_keys:
        passed = present
    else:
        # Strip by default (prevents accidental network calls during tests).
        for k in secret_vars:
            base.pop(k, None)
        stripped = present

    allowlist_record = ["PATH", "PYTHONPATH", "VIRTUAL_ENV", "CONDA_PREFIX", "HOME", "SHELL"]
    env_record = {k: os.environ.get(k) for k in allowlist_record if os.environ.get(k) is not None}

    return base, {"env_allowlist": env_record, "stripped_secret_vars": stripped, "passed_secret_vars": passed}


def _invoke_massgen_advisory(
    *,
    policy: Policy,
    prompt: str,
    run_dir: Path,
) -> Tuple[bool, Dict[str, Any], Path, Path, Path]:
    """
    Real MassGen invocation (advisory-only from CohOS perspective):
    - Calls the massgen CLI
    - Captures stdout/stderr
    - Records invocation metadata (sanitized env)
    """
    massgen_bin = (Path(sys.executable).resolve().parent / "massgen")
    if not massgen_bin.exists():
        # Fall back to PATH if needed.
        massgen_bin = Path("massgen")

    stdout_path = run_dir / "massgen_stdout.log"
    stderr_path = run_dir / "massgen_stderr.log"
    inv_path = run_dir / "massgen_invocation.json"

    base_cmd: List[str] = [str(massgen_bin), "--no-display", "--debug"]
    if policy.massgen_args:
        base_cmd.extend([str(x) for x in policy.massgen_args])

    # Hard timeout override for orchestrator.
    base_cmd.extend(["--orchestrator-timeout", str(int(policy.orchestrator_timeout_s))])

    # Positional question
    base_cmd.append(prompt)

    env, env_meta = _env_sanitized(policy)

    t0 = time.time()
    with stdout_path.open("w", encoding="utf-8") as out, stderr_path.open("w", encoding="utf-8") as err:
        try:
            cp = subprocess.run(
                base_cmd,
                cwd=str(run_dir),
                env=env,
                stdout=out,
                stderr=err,
                text=True,
                timeout=max(10, int(policy.orchestrator_timeout_s) + 30),
            )
            rc = int(cp.returncode)
            ok = (rc == 0)
        except subprocess.TimeoutExpired as e:
            ok = False
            rc = 124
            err.write(f"\n[COHOS] TimeoutExpired: {e}\n")
        except Exception as e:
            ok = False
            rc = 2
            err.write(f"\n[COHOS] Exception: {type(e).__name__}: {e}\n")

    wall_s = round(time.time() - t0, 3)

    inv = {
        "schema": "cohos.massgen_invocation.v1",
        "cmd": base_cmd,
        "cwd": str(run_dir),
        "returncode": rc,
        "ok": ok,
        "wall_s": wall_s,
        **env_meta,
    }
    inv_path.write_text(json.dumps(inv, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    advisory = {
        "schema": "massgen.advisory.v1",
        "ok": ok,
        "returncode": rc,
        "stdout_log": str(stdout_path.name),
        "stderr_log": str(stderr_path.name),
        "invocation": str(inv_path.name),
        "notes": "CohOS wrapper treats MassGen as advisory-only; decision authority remains external.",
    }

    return ok, advisory, stdout_path, stderr_path, inv_path


def cohos_run(*, policy_path: str, prompt: str, out_dir: str) -> str:
    run_id = f"massgen-cohos-{uuid.uuid4().hex[:12]}"
    bundle = init_bundle(out_dir)

    decision = "REFUSE"
    reason = reasons.INTERNAL_ERROR_STEP_FAIL
    details: Dict[str, Any] = {"run_id": run_id}
    policy_id = "unknown"

    try:
        policy_obj = _load_json(policy_path)
        try:
            policy = _parse_policy(policy_obj)
            policy_id = policy.policy_id
        except Exception as e:
            policy_id = str(policy_obj.get("policy_id") or "unknown")
            decision = "REFUSE"
            reason = reasons.POLICY_INVALID
            details.update({"error": f"POLICY_INVALID: {e}"})
            write_policy_copy(bundle, policy_obj)
            write_decision(bundle, decision=decision, reason=reason, policy_id=policy_id, run_id=run_id, details=details)
            write_manifest_and_hashes(bundle)
            return str(bundle.run_dir)

        write_policy_copy(bundle, policy_obj)

        ok, advisory, sp_out, sp_err, sp_inv = _invoke_massgen_advisory(policy=policy, prompt=prompt, run_dir=bundle.run_dir)

        advisory_path = bundle.run_dir / "massgen_advisory.json"
        advisory_path.write_text(json.dumps(advisory, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        # Gate per policy.
        if policy.require_massgen_success and not ok:
            decision = "REFUSE"
            reason = reasons.INTERNAL_ERROR_STEP_FAIL
            details.update({"massgen_ok": False})
        else:
            decision = "ALLOW"
            reason = reasons.ALLOW_ALL_CHECKS_PASS
            details.update({"massgen_ok": ok})

        write_decision(bundle, decision=decision, reason=reason, policy_id=policy_id, run_id=run_id, details=details)
        write_manifest_and_hashes(bundle, extra_files=[advisory_path, sp_out, sp_err, sp_inv])
        return str(bundle.run_dir)

    except Exception as e:
        details.update({"error": f"EXCEPTION: {type(e).__name__}: {e}"})
        try:
            write_decision(bundle, decision="REFUSE", reason=reasons.INTERNAL_ERROR_STEP_FAIL, policy_id=policy_id, run_id=run_id, details=details)
            write_manifest_and_hashes(bundle)
        except Exception:
            pass
        return str(bundle.run_dir)


def _usage() -> str:
    return (
        "Usage:\n"
        "  python3 -m massgen_ext.cohos.run --policy <policy.json> --out <run_dir> --prompt \"...\"\n"
    )


def main(argv: Optional[list[str]] = None) -> int:
    argv = argv or sys.argv[1:]
    args = {"--policy": None, "--out": None, "--prompt": None}

    i = 0
    while i < len(argv):
        k = argv[i]
        if k in args:
            if i + 1 >= len(argv):
                print(_usage(), file=sys.stderr)
                return 2
            args[k] = argv[i + 1]
            i += 2
        else:
            print(f"Unknown arg: {k}\n{_usage()}", file=sys.stderr)
            return 2

    if not args["--policy"] or not args["--out"] or not args["--prompt"]:
        print(_usage(), file=sys.stderr)
        return 2

    run_dir = cohos_run(policy_path=args["--policy"], prompt=args["--prompt"], out_dir=args["--out"])
    print(run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
