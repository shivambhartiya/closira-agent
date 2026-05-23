import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from agent.state import ConversationState

DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-20250514"


@dataclass
class LLMClient:
    provider: str
    client: Any
    model: str
    base_url: Optional[str] = None


def _env_first(*names: str) -> Optional[str]:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def create_llm_client() -> LLMClient:
    """
    Build the configured model client from environment variables.

    Supported providers:
    - openai: OpenAI API
    - openai_compatible: Hugging Face, OpenRouter, Together, Fireworks, Groq, etc.
    - anthropic: Anthropic Claude API
    """
    provider = os.environ.get("LLM_PROVIDER", "").strip().lower()
    if not provider:
        provider = "anthropic" if os.environ.get("ANTHROPIC_API_KEY") else "openai"

    provider_aliases = {
        "hf": "openai_compatible",
        "huggingface": "openai_compatible",
        "hugging_face": "openai_compatible",
        "openai-compatible": "openai_compatible",
        "qwen": "openai_compatible",
        "chatgpt": "openai",
        "claude": "anthropic",
    }
    provider = provider_aliases.get(provider, provider)

    if provider in {"openai", "openai_compatible"}:
        from openai import OpenAI

        api_key = _env_first("LLM_API_KEY", "OPENAI_API_KEY")
        if not api_key:
            raise ValueError("LLM_API_KEY or OPENAI_API_KEY not set. Add it to .env.")

        model = _env_first("LLM_MODEL", "OPENAI_MODEL") or DEFAULT_OPENAI_MODEL
        base_url = _env_first("LLM_BASE_URL", "OPENAI_BASE_URL")
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        return LLMClient(provider=provider, client=OpenAI(**kwargs), model=model, base_url=base_url)

    if provider == "anthropic":
        import anthropic

        api_key = _env_first("LLM_API_KEY", "ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("LLM_API_KEY or ANTHROPIC_API_KEY not set. Add it to .env.")

        model = _env_first("LLM_MODEL", "ANTHROPIC_MODEL") or DEFAULT_ANTHROPIC_MODEL
        return LLMClient(provider=provider, client=anthropic.Anthropic(api_key=api_key), model=model)

    raise ValueError(
        "Unsupported LLM_PROVIDER. Use openai, openai_compatible, or anthropic."
    )


def _normalise_messages_for_openai(messages: list) -> list:
    """
    Preserve the full conversation in OpenAI Chat Completions format.

    The CLI stores the assistant's greeting in state.messages because it is part of the
    customer-visible transcript. We keep that history intact and avoid provider-specific
    assumptions outside this small adapter.
    """
    if not messages:
        return [{"role": "user", "content": "No prior conversation history."}]

    normalised = []
    for message in messages:
        role = message.get("role", "user")
        if role not in {"user", "assistant", "system"}:
            role = "user"
        normalised.append({"role": role, "content": str(message.get("content", ""))})
    return normalised


def _normalise_messages_for_anthropic(messages: list) -> list:
    if not messages:
        return [{"role": "user", "content": "No prior conversation history."}]

    normalised = []
    for message in messages:
        role = message.get("role", "user")
        if role not in {"user", "assistant"}:
            role = "user"
        normalised.append({"role": role, "content": str(message.get("content", ""))})

    if normalised[0].get("role") != "user":
        normalised.insert(
            0,
            {
                "role": "user",
                "content": "Conversation context follows. Use it only as history.",
            },
        )
    return normalised


def _extract_json(raw: str) -> dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def _should_retry_without_response_format(exc: Exception) -> bool:
    text = str(exc).lower()
    return type(exc).__name__ == "BadRequestError" and (
        "response_format" in text or "json" in text
    )


def _call_openai_compatible(llm: LLMClient, system_prompt: str, messages: list, max_tokens: int) -> str:
    api_messages = [{"role": "system", "content": system_prompt}]
    api_messages.extend(_normalise_messages_for_openai(messages))

    kwargs = {
        "model": llm.model,
        "messages": api_messages,
        "max_tokens": max_tokens,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    try:
        response = llm.client.chat.completions.create(**kwargs)
    except Exception as exc:
        if not _should_retry_without_response_format(exc):
            raise
        kwargs.pop("response_format")
        response = llm.client.chat.completions.create(**kwargs)

    return (response.choices[0].message.content or "").strip()


def _call_anthropic(llm: LLMClient, system_prompt: str, messages: list, max_tokens: int) -> str:
    response = llm.client.messages.create(
        model=llm.model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=_normalise_messages_for_anthropic(messages),
    )
    return response.content[0].text.strip()


def call_llm(llm: LLMClient, system_prompt: str, messages: list, max_tokens: int = 1000) -> dict:
    """
    Central model API caller. Always returns parsed JSON.
    All model calls in this project request JSON output - never free prose.
    """
    try:
        if llm.provider in {"openai", "openai_compatible"}:
            raw = _call_openai_compatible(llm, system_prompt, messages, max_tokens)
        elif llm.provider == "anthropic":
            raw = _call_anthropic(llm, system_prompt, messages, max_tokens)
        else:
            raise ValueError(f"Unsupported provider: {llm.provider}")
    except Exception as exc:
        return {
            "reply": "I'm sorry, I'm having trouble connecting to the AI service right now. Please try again shortly.",
            "can_answer": False,
            "sop_gap": "api_error",
            "escalate": False,
            "escalation_reason": "api_error",
            "confidence": "low",
            "should_escalate": False,
            "trigger": None,
            "reasoning": f"{llm.provider} API call failed: {type(exc).__name__}"
        }

    try:
        return _extract_json(raw)
    except (json.JSONDecodeError, TypeError):
        return {
            "reply": raw,
            "can_answer": False,
            "sop_gap": "json_parse_error",
            "escalate": False,
            "escalation_reason": "parse_error",
            "confidence": "low",
            "should_escalate": False,
            "trigger": None,
            "reasoning": "JSON parse failed"
        }


def check_escalation(llm: LLMClient, state: ConversationState, user_input: str, sop_text: str) -> dict:
    """
    Pre-filter that runs before every stage handler.
    Detects escalation triggers independently of the main stage logic.
    This dual-layer approach ensures no trigger is missed.
    """
    qualification_state = json.dumps(state.qualification, indent=2)

    system_prompt = f"""You are an escalation classifier for a customer support AI at an aesthetics clinic.

Use the SOP below as the only business context when judging whether the message is in scope.

SOP DATA:
---
{sop_text}
---

Given the customer's latest message, identify whether any escalation condition is present.
Latest customer message: {user_input!r}
Current workflow stage: {state.stage}
Last assistant message: {_last_assistant_message(state.messages)!r}
Current qualification state:
{qualification_state}

Escalation conditions:
1. ANGRY_SENTIMENT - customer is clearly frustrated, upset, or using aggressive language
2. COMPLAINT - customer is making a formal complaint about a service or experience
3. MEDICAL_QUESTION - customer is asking for medical advice, contraindications, or health guidance
4. PRICING_NEGOTIATION - customer is actively trying to negotiate a lower price, asking for a discount, haggling, or refusing to pay the listed price
5. EXPLICIT_ESCALATION - customer explicitly asks to speak to a human, manager, agent, staff member, or real person (for example: "speak to someone", "talk to a human", "get me your manager")
6. OUT_OF_SCOPE - question is completely unrelated to aesthetics, beauty, the clinic, or the current lead-qualification task

Do not escalate routine SOP gaps such as services not listed, parking, or availability details.
Those are handled by the FAQ stage unless another escalation condition is also present.
If the current workflow stage is "qualification" and the latest message plausibly answers business type, team size, or current communication tools, do NOT classify it as OUT_OF_SCOPE.
Short factual qualification answers such as "5", "tech", "WhatsApp", "insta", "email", or "phone" are expected and are NOT escalation triggers.
PRICING_NEGOTIATION does not mean a normal pricing enquiry. A customer asking "how much does X cost?", "what are your prices?", or "what is the price of 12 units?" is NOT negotiating and should not be escalated.
EXPLICIT_ESCALATION does not mean booking intent. A customer saying "book", "I want to book", "okay book", or "how do I book" is NOT asking for a human. It is a booking enquiry that should be answered from the SOP.

Respond ONLY in valid JSON with no prose before or after:
{{
  "should_escalate": false,
  "trigger": null,
  "confidence": "high",
  "reasoning": "one sentence explanation"
}}"""

    return call_llm(llm, system_prompt, state.messages, max_tokens=300)


def _last_assistant_message(messages: list) -> str:
    for message in reversed(messages):
        if message.get("role") == "assistant":
            return str(message.get("content", ""))
    return ""


def normalise_escalation_reason(reason: Optional[str]) -> str:
    text = str(reason or "unspecified").strip()
    token = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").upper()
    aliases = {
        "EXPLICIT_REQUEST_FOR_HUMAN_AGENT": "EXPLICIT_ESCALATION",
        "HUMAN_AGENT": "EXPLICIT_ESCALATION",
        "HUMAN_REQUEST": "EXPLICIT_ESCALATION",
        "PRICING_NEGOTIATION": "PRICING_NEGOTIATION",
        "OUT_OF_SCOPE": "OUT_OF_SCOPE",
        "COMPLAINT": "COMPLAINT",
        "ANGRY_SENTIMENT": "ANGRY_SENTIMENT",
        "MEDICAL_QUESTION": "MEDICAL_QUESTION",
    }
    return aliases.get(token, text)


def trigger_escalation(state: ConversationState, reason: str) -> str:
    """Marks state as escalated, logs it, and returns a warm handoff message."""
    reason = normalise_escalation_reason(reason)
    state.escalation_triggered = True
    state.escalation_reason = reason
    state.escalation_timestamp = datetime.now().isoformat()
    state.stage = "escalated"
    _log_escalation(state)
    return (
        "I completely understand, and I want to make sure you get the best help possible. "
        "I'm passing you over to one of our team members right now who can assist you directly. "
        f"[ESCALATED - Reason: {reason}]"
    )


def _log_escalation(state: ConversationState):
    """Writes escalation event to logs/."""
    log_dir = Path(__file__).resolve().parents[1] / "logs"
    log_dir.mkdir(exist_ok=True)
    log_entry = {
        "session_id": state.session_id,
        "escalation_reason": state.escalation_reason,
        "escalation_timestamp": state.escalation_timestamp,
        "turn_count": state.turn_count,
        "unanswered_count": state.unanswered_count,
        "sop_gaps": state.sop_gaps
    }
    with open(log_dir / f"escalation_{state.session_id}.json", "w", encoding="utf-8") as f:
        json.dump(log_entry, f, indent=2)
