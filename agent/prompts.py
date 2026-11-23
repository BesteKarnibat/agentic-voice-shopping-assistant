"""Load prompts from prompts/*.md (only the BEGIN/END PROMPT section is sent to the LLM)."""

from __future__ import annotations

import re
from functools import lru_cache

from config.paths import ROOT

PROMPTS_DIR = ROOT / "prompts"
_SECTION = re.compile(r"<!--\s*BEGIN PROMPT\s*-->(.*?)<!--\s*END PROMPT\s*-->", re.S)


@lru_cache(maxsize=None)
def _raw(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def prompt_section(name: str) -> str:
    """The BEGIN/END PROMPT section of prompts/<name>.md (whole file if there are no markers)."""
    text = _raw(name)
    m = _SECTION.search(text)
    return (m.group(1) if m else text).strip()


def load_prompt(name: str, **values: str) -> str:
    """Prompt section with `{{key}}` placeholders replaced."""
    text = prompt_section(name)
    for key, val in values.items():
        text = text.replace("{{" + key + "}}", val)
    leftover = re.findall(r"\{\{(\w+)\}\}", text)
    if leftover:
        raise KeyError(f"Prompt '{name}' has unfilled placeholders: {leftover}")
    return text


def system_prompt_for(node_prompt: str, **values: str) -> str:
    """Shared system prompt + the node's own prompt."""
    return prompt_section("system") + "\n\n" + load_prompt(node_prompt, **values)


def guardrail_templates() -> dict[str, str]:
    """Response templates from prompts/guardrails.md, keyed by safety category ({} if not found)."""
    text = _raw("guardrails")
    out: dict[str, str] = {}
    for block in re.split(r"\n(?=### )", text):
        head = block.splitlines()[0]
        m = re.match(r"###\s*\d+\.\s*`(\w+)`", head)
        key = m.group(1) if m else ("out_of_scope" if "out of scope" in head.lower() else None)
        if not key:
            continue
        t = re.search(r"Template:\s*\n((?:>.*\n?)+)", block)
        if t:
            quoted = " ".join(line.lstrip("> ").strip() for line in t.group(1).splitlines())
            out[key] = quoted.strip().strip('"').strip("“”")
    return out
