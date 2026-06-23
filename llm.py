"""LLM access + structured-output runner.

One place that knows how to talk to the model. Swapping providers is a single
env var (`LLM_PROVIDER`).

Structured output is enforced in a *model-agnostic* way: we append the Pydantic
schema to the prompt, ask for JSON, then parse + validate it, with one corrective
retry on failure. This is the guardrail against schema drift, and unlike the
provider's native structured-output/tool-calling mode it works on every model —
including free OpenRouter models that don't support function calling.
"""

from __future__ import annotations

import os
from typing import Type, TypeVar

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel

from logconf import get_logger
from prompts import SYSTEM_PROMPT

load_dotenv()

log = get_logger("llm")

T = TypeVar("T", bound=BaseModel)

_DEFAULT_MODELS = {
    "openai": "gpt-4o",
    "anthropic": "claude-sonnet-4-6",
    # OpenRouter uses namespaced model ids. Pick a tool-calling-capable model.
    "openrouter": "openai/gpt-4o",
}

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def get_llm(temperature: float = 0.2):
    """Return a chat model for the configured provider."""
    provider = os.getenv("LLM_PROVIDER", "openai").lower()
    model = os.getenv("LLM_MODEL") or _DEFAULT_MODELS.get(provider, "gpt-4o")

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=model, temperature=temperature)

    if provider == "openrouter":
        # OpenRouter is OpenAI-compatible: reuse ChatOpenAI with a custom base_url.
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model,
            temperature=temperature,
            base_url=OPENROUTER_BASE_URL,
            api_key=os.environ.get("OPENROUTER_API_KEY"),
        )

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=model, temperature=temperature)

    raise ValueError(
        f"Unknown LLM_PROVIDER={provider!r}. Use 'openai', 'anthropic', or 'openrouter'."
    )


def _text(content) -> str:
    """Coerce a message's content (str or list-of-blocks) into plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text", ""))
            else:
                parts.append(str(block))
        return "".join(parts)
    return str(content)


def run_structured(
    output_model: Type[T],
    user_prompt: str,
    *,
    temperature: float = 0.2,
    max_retries: int = 1,
) -> T:
    """Invoke the LLM and return a validated instance of `output_model`.

    Model-agnostic: appends the schema, asks for JSON, parses + validates with
    Pydantic, and retries once with a correction message on a parse failure.
    """
    provider = os.getenv("LLM_PROVIDER", "openai").lower()
    model = os.getenv("LLM_MODEL") or _DEFAULT_MODELS.get(provider, "gpt-4o")
    log.info("  · LLM call → %s  (schema=%s, temp=%s)", model, output_model.__name__, temperature)

    llm = get_llm(temperature)
    parser = PydanticOutputParser(pydantic_object=output_model)

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"{user_prompt}\n\n{parser.get_format_instructions()}\n\n"
                "Return ONLY the JSON object — no markdown fences, no commentary."
            )
        ),
    ]

    last_err: Exception | None = None
    for attempt in range(max_retries + 1):
        response = llm.invoke(messages)
        text = _text(response.content)
        try:
            result = parser.parse(text)
            log.info("  · LLM returned valid %s", output_model.__name__)
            return result
        except Exception as exc:  # noqa: BLE001 — feed the error back for a retry
            last_err = exc
            log.warning("  · parse failed (attempt %d/%d): %s", attempt + 1, max_retries + 1, exc)
            messages.append(HumanMessage(content=str(text)[:2000]))
            messages.append(
                HumanMessage(
                    content=(
                        f"That could not be parsed ({exc}). Return ONLY valid JSON "
                        f"matching the schema. No markdown, no extra text."
                    )
                )
            )

    raise ValueError(
        f"Failed to get valid {output_model.__name__} after "
        f"{max_retries + 1} attempts. Last error: {last_err}"
    )
