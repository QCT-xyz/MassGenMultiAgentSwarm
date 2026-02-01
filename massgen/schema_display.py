from __future__ import annotations

import json
from typing import Any, Dict, Optional


def _basic_schema(show_examples: bool = False) -> Dict[str, Any]:
    """
    Minimal schema payload for MassGen CLI --show-schema.

    This avoids extra dependencies and provides a stable, machine-readable contract.
    It can be extended later to introspect richer configuration structures.
    """
    schema: Dict[str, Any] = {
        "schema": "massgen.config.schema.v0",
        "type": "object",
        "required": ["agents"],
        "properties": {
            "agents": {
                "type": "array",
                "items": {"type": "object"},
                "description": "List of agent configurations (backend/model/system/etc.).",
                "minItems": 1,
            },
            "orchestrator": {
                "type": "object",
                "description": "Orchestrator settings (timeouts, retries, coordination).",
            },
            "tools": {
                "type": "object",
                "description": "Tool configuration (filesystem, code execution, MCP, etc.).",
            },
        },
    }

    if show_examples:
        schema["examples"] = [
            {
                "name": "single_agent_minimal",
                "config": {
                    "agents": [
                        {"name": "agent0", "backend": "openai", "model": "gpt-4o-mini"}
                    ]
                },
            },
            {
                "name": "two_agent_debate",
                "config": {
                    "agents": [
                        {"name": "agent0", "backend": "openai", "model": "gpt-4o-mini"},
                        {"name": "agent1", "backend": "claude", "model": "claude-sonnet-4-20250514"},
                    ],
                    "orchestrator": {"mode": "debate", "max_rounds": 4},
                },
            },
        ]
    return schema


def show_schema(*, backend: Optional[str] = None, show_examples: bool = False, **kwargs: Any) -> None:
    """
    Entry point used by massgen.cli when --show-schema is requested.

    Keep exact kwargs for CLI compatibility:
      - backend
      - show_examples

    Accept **kwargs defensively to avoid breaking if CLI expands.
    """
    _ = backend
    _ = kwargs
    obj = _basic_schema(show_examples=show_examples)
    print(json.dumps(obj, indent=2, sort_keys=True))
