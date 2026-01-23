from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class BundlePaths:
    run_dir: Path
    decision_path: Path
    policy_copy_path: Path
    manifest_path: Path
    hashes_path: Path


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_json_atomic(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def init_bundle(run_dir: str) -> BundlePaths:
    rd = Path(run_dir).expanduser().resolve()
    rd.mkdir(parents=True, exist_ok=True)
    return BundlePaths(
        run_dir=rd,
        decision_path=rd / "decision.json",
        policy_copy_path=rd / "policy.json",
        manifest_path=rd / "manifest.json",
        hashes_path=rd / "hashes.json",
    )


def write_policy_copy(bundle: BundlePaths, policy_obj: Dict[str, Any]) -> None:
    _write_json_atomic(bundle.policy_copy_path, policy_obj)


def write_decision(
    bundle: BundlePaths,
    *,
    decision: str,
    reason: str,
    policy_id: str,
    run_id: str,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    obj: Dict[str, Any] = {
        "schema": "cohos.decision.v1",
        "run_id": run_id,
        "policy_id": policy_id,
        "decision": decision,
        "reason": reason,
        "ts_utc": _utc_now_iso(),
        "details": details or {},
    }
    _write_json_atomic(bundle.decision_path, obj)


def write_manifest_and_hashes(bundle: BundlePaths, extra_files: Optional[List[Path]] = None) -> None:
    files: List[Path] = [
        bundle.decision_path,
        bundle.policy_copy_path,
    ]
    if extra_files:
        files.extend(extra_files)

    # Only include files that exist (defensive).
    files = [p for p in files if p.exists()]

    manifest = {
        "schema": "cohos.manifest.v1",
        "run_dir": str(bundle.run_dir),
        "ts_utc": _utc_now_iso(),
        "files": [str(p.relative_to(bundle.run_dir)) for p in files],
    }
    _write_json_atomic(bundle.manifest_path, manifest)

    hashes = {
        "schema": "cohos.hashes.v1",
        "ts_utc": _utc_now_iso(),
        "sha256": {str(p.relative_to(bundle.run_dir)): _sha256_file(p) for p in files + [bundle.manifest_path]},
    }
    _write_json_atomic(bundle.hashes_path, hashes)
