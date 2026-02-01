#!/usr/bin/env bash
set -euo pipefail

RUN_DIR="${1:-./runs/demo_run_1}"
PROMPT="${2:-Propose and debate two designs for reliable multi-agent coordination.}"

POLICY="demo/policy_demo.json"

cat > "$POLICY" <<JSON
{
  "policy_id": "cohos.demo.lmstudio.massgen",
  "config_path": "examples/cohos/openai_team.yaml",
  "lmstudio_base_url": "http://127.0.0.1:1234/v1",
  "lmstudio_api_key": "local",
  "timeout_s": 360,
  "orchestrator_timeout_s": 300
}
JSON

python scripts/cohos_run_lmstudio.py --policy "$POLICY" --out "$RUN_DIR" --prompt "$PROMPT"
python scripts/extract_agent_artifacts.py --run-dir "$RUN_DIR"
echo "Demo complete: $RUN_DIR"
