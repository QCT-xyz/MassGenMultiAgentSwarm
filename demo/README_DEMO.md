# QCT Demo: CohOS-governed MassGen on LM Studio (local, no quotas)

## What this does
Runs a multi-agent MassGen workflow against LM Studio (local MLX model) and emits a CohOS evidence bundle:
- decision.json, policy.json, manifest.json, hashes.json
- MassGen stdout/stderr + invocation record
- Extracted role artifacts: context, candidates, final

## Prerequisites
1) LM Studio is running a model and the Local Server is enabled:
   - Base URL: http://127.0.0.1:1234/v1
   - Model id example: qwen2.5-coder-7b-instruct-mlx
2) Python venv is active and dependencies installed:
   - pip install -e .
3) Scripts exist:
   - scripts/run_massgen_lmstudio.py
   - scripts/cohos_run_lmstudio.py
   - scripts/extract_agent_artifacts.py

## Baseline config used
- examples/cohos/openai_team.yaml

## Run the demo
From repo root:

  bash demo/run_demo.sh

## Expected output
A run directory like:
  runs/demo_run_1/

Contains:
- decision.json (ALLOW if successful)
- policy.json
- manifest.json
- hashes.json
- massgen_stdout.log, massgen_stderr.log, massgen_invocation.json
- artifacts/index.txt
- artifacts/context_information_gatherer.txt
- artifacts/candidates_domain_expert.txt
- artifacts/final_synthesizer.txt

## Notes
- This demo uses LM Studio via the OpenAI-compatible HTTP API.
- No OpenAI cloud keys are required.
