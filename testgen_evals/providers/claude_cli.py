"""Backend that shells out to the Claude Code CLI (``claude -p --output-format json``).

This is the backend used for the committed results. It needs no API key: the CLI is
already authenticated on the developer's machine. Tools, hooks, slash commands and
MCP servers are disabled so the call is a single plain completion.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess

from .base import Completion, Provider


class ClaudeCliProvider(Provider):
    name = "claude-cli"

    @property
    def default_model(self) -> str:
        return os.environ.get("TESTGEN_CLAUDE_CLI_MODEL", "sonnet")

    def _call(self, prompt: str, system: str) -> Completion:
        exe = shutil.which("claude")
        if exe is None:
            raise RuntimeError("`claude` CLI not found on PATH")
        cmd = [
            exe,
            "-p",
            prompt,
            "--output-format",
            "json",
            "--model",
            self.model,
            "--tools",
            "",
            "--max-turns",
            "1",
            "--disable-slash-commands",
            "--strict-mcp-config",
        ]
        if system:
            cmd += ["--system-prompt", system]
        # stderr is captured separately: the CLI may print hook warnings there.
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300, check=False)
        if proc.returncode != 0:
            raise RuntimeError(f"claude CLI exited {proc.returncode}: {proc.stderr.strip()[:500]}")
        data = json.loads(proc.stdout)
        if data.get("is_error"):
            raise RuntimeError(f"claude CLI error: {data.get('result')}")
        usage = data.get("usage") or {}
        model_usage = data.get("modelUsage") or {}
        model = next(iter(model_usage), self.model)
        inp = usage.get("input_tokens")
        if inp is not None:
            inp += usage.get("cache_creation_input_tokens", 0)
            inp += usage.get("cache_read_input_tokens", 0)
        return Completion(
            text=str(data.get("result", "")),
            latency_ms=float(data.get("duration_api_ms") or 0.0),
            model=model,
            input_tokens=inp,
            output_tokens=usage.get("output_tokens"),
            cost_usd=data.get("total_cost_usd"),
        )
