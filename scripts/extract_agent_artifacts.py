#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Dict, List

AGENT_LINE = re.compile(r"^\[([A-Za-z0-9_\-]+)\]\s?(.*)$")

def load_lines(p: Path) -> List[str]:
    return p.read_text(encoding="utf-8", errors="replace").splitlines()

def reconstruct_from_stdout(stdout_path: Path) -> Dict[str, str]:
    buckets: Dict[str, List[str]] = {}
    for line in load_lines(stdout_path):
        m = AGENT_LINE.match(line.strip("\n"))
        if not m:
            continue
        agent = m.group(1)
        chunk = m.group(2)
        # ignore pure empties to reduce noise
        if chunk is None:
            continue
        buckets.setdefault(agent, []).append(chunk)
    return {k: "".join(v).strip() for k, v in buckets.items() if "".join(v).strip()}

def write_artifact(run_dir: Path, rel: str, content: str) -> Path:
    out = run_dir / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content.strip() + "\n", encoding="utf-8")
    return out

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True, help="Run directory containing massgen_stdout.log")
    args = ap.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    stdout_path = run_dir / "massgen_stdout.log"
    if not stdout_path.exists():
        raise SystemExit(f"Missing {stdout_path}")

    texts = reconstruct_from_stdout(stdout_path)

    # Heuristic mapping by canonical names used in your config
    gather = texts.get("information_gatherer") or texts.get("gatherer") or ""
    expert  = texts.get("domain_expert") or texts.get("expert") or ""
    synth   = texts.get("synthesizer") or texts.get("synth") or ""

    written = []
    if gather:
        written.append(write_artifact(run_dir, "artifacts/context_information_gatherer.txt", gather))
    if expert:
        written.append(write_artifact(run_dir, "artifacts/candidates_domain_expert.txt", expert))
    if synth:
        written.append(write_artifact(run_dir, "artifacts/final_synthesizer.txt", synth))

    # Always write an index for auditability
    idx = run_dir / "artifacts" / "index.txt"
    idx.parent.mkdir(parents=True, exist_ok=True)
    idx.write_text("Written artifacts:\n" + "\n".join(str(p.relative_to(run_dir)) for p in written) + "\n", encoding="utf-8")

    print(str(idx))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
