# MassGen + CohOS Governed Local AI Demo

This repository demonstrates post-hoc governance of multi-agent AI execution using a local language model. The system allows AI agents to run, then decides whether the result is admissible based on observed behavior.

This is not an alignment framework. This is execution governance.

---

## What problem this solves

Modern AI systems execute even when they should not be trusted. They may thrash internally, restart repeatedly, exceed latency or stability envelopes, or produce results only after coercive retries. Most systems still treat this as success.

This project demonstrates a different principle:

AI execution is cheap. AI permission must be earned.

---

## What is novel here

This repository shows a working system where:

- AI runs
- Governance happens after execution
- Decisions are based on measured behavior, not promises
- Outcomes are graded: ALLOW, MARGINAL, REFUSE
- Every decision emits verifiable artifacts

No model claims are trusted. No safety is assumed.

---

## High-level architecture

User Prompt  
→ Local LLM (LM Studio, MLX)  
→ Multi-agent orchestration (MassGen)  
→ Observed behavior (restarts, latency, churn)  
→ CohOS policy evaluation  
→ ALLOW / MARGINAL / REFUSE plus evidence bundle

The system does not prevent execution. It determines whether the result is admissible.

---

## Components

### Local model (untrusted substrate)
- LM Studio
- MLX-accelerated local model (example: qwen2.5-coder-7b-instruct-mlx)
- OpenAI-compatible HTTP API
- No cloud keys, no quotas

The model is treated as unreliable by default.

### Multi-agent execution (MassGen)
MassGen is used to run multiple agents, allow self-revision, and expose instability and churn. It is treated as a stress generator, not a trust anchor.

### Governance layer (CohOS)
CohOS sits above execution and evaluates:
- Did the run complete?
- How many restarts occurred?
- How long did it take?
- Did the system thrash or converge?

Based on policy thresholds, CohOS emits:
- decision.json
- policy.json
- manifest.json
- hashes.json

This is refusal-first governance: execution is allowed, permission is conditional.

---

## Decision semantics

CohOS produces one of three outcomes:

### ALLOW
Execution completed and metrics are within the defined envelope.

### MARGINAL
Execution completed but exceeded soft thresholds. Result is usable but flagged.

### REFUSE
Execution failed or exceeded hard thresholds. Result must not be acted upon.

These are post-hoc decisions based on evidence.

---

## Running the demo

### Prerequisites

1) LM Studio
- Local server enabled
- Endpoint: http://127.0.0.1:1234/v1
- Any supported local model

2) Python environment
pip install -e .

### One-command demo

From repository root:
bash demo/run_demo.sh

This runs a multi-agent job locally, evaluates behavior via CohOS, and emits a complete evidence bundle.

---

## Output structure

After running, you will see a directory like:

runs/demo_run_1/
- decision.json
- policy.json
- manifest.json
- hashes.json
- massgen_stdout.log
- massgen_stderr.log
- massgen_invocation.json
- artifacts/
  - context_information_gatherer.txt
  - candidates_domain_expert.txt
  - final_synthesizer.txt
  - index.txt
- .massgen/ (MassGen internals and logs)

Key files:
- decision.json: final governance outcome
- manifest.json and hashes.json: evidence integrity
- artifacts/: human-readable role outputs

---

## Governance policy

The demo policy enforces thresholds such as:
- maximum allowed restarts
- maximum wall-clock runtime
- hard refusal limits

Thresholds are explicit and inspectable.

---

## Important design choices

### Why voting is disabled in production mode
Voting loops caused instability for local models. Tool coercion inflated prompts and retries. Deterministic synthesis proved more reliable. This is a measured decision, not a theoretical one.

### Why tools may still appear in logs
Tools may be present in the schema, but coercive enforcement is gated. Agents are not forced into tool loops. Governance relies on behavior, not tool usage.

---

## What this is not

This repository does not claim:
- alignment solved
- correctness guarantees
- safety proofs
- model reliability

It demonstrates operational governance, not moral alignment.

---

## Relation to WCCT (conceptual)
WCCT motivates the idea that coherence can be observed and enforced. This repository demonstrates an operational analogue: coherence as measured system behavior enforced via policy, without assuming correctness of the underlying substrate.

No physics claims are made here.

---

## Repository state
Baseline tag: qct-demo-v0.1.0  
This tag is frozen and reproducible. New work should occur in branches or new tags.

