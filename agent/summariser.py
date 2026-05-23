import json
import os
from pathlib import Path
from typing import Optional

from agent.state import ConversationState
from agent.escalation import call_llm


def generate_summary(client, state: ConversationState, sop_text: str) -> dict:
    """
    Stage 4 - Conversation Summary.
    Called at end of session. Produces a structured JSON summary and saves a session log.
    """
    qualification_json = json.dumps(state.qualification, indent=2)
    sop_gaps_text = ", ".join(state.sop_gaps) if state.sop_gaps else "None"

    system_prompt = f"""You are summarising a completed customer support conversation for Bloom Aesthetics Clinic.

You will be given the full conversation history. Produce a structured summary that will be used by the clinic's team to follow up appropriately.

SOP DATA (for context only, do not invent beyond it):
---
{sop_text}
---

Context:
- SOP gaps encountered (questions the AI could not answer): {sop_gaps_text}
- Escalation triggered: {state.escalation_triggered}
- Escalation reason: {state.escalation_reason or 'N/A'}
- Lead qualification state: {qualification_json}
- Total turns: {state.turn_count}

Respond ONLY in valid JSON with no prose before or after:
{{
  "customer_intent": "Brief description of what the customer was trying to achieve",
  "key_details_collected": {{
    "business_type": "...",
    "team_size": "...",
    "current_tools": "...",
    "topics_asked_about": ["Botox pricing", "booking process"]
  }},
  "sop_gaps": ["list of question topics the SOP could not answer"],
  "escalation": {{
    "triggered": false,
    "reason": null,
    "timestamp": null
  }},
  "recommended_next_action": "e.g. Follow up with a personalised Botox pricing quote",
  "sentiment_overall": "positive",
  "qualification_status": "complete"
}}

sentiment_overall must be one of: positive, neutral, negative
qualification_status must be one of: complete, partial, not_started"""

    result = call_llm(client, system_prompt, state.messages, max_tokens=1500)

    # Fill in application-owned state because it is more reliable than LLM recollection.
    result["escalation"] = {
        "triggered": state.escalation_triggered,
        "reason": state.escalation_reason,
        "timestamp": state.escalation_timestamp
    }
    result["sop_gaps"] = state.sop_gaps
    result["qualification_status"] = get_qualification_status(state.qualification)
    result["sentiment_overall"] = _normalise_sentiment(
        result.get("sentiment_overall"), state
    )

    details = result.setdefault("key_details_collected", {})
    details["business_type"] = state.qualification.get("business_type")
    details["team_size"] = state.qualification.get("team_size")
    details["current_tools"] = state.qualification.get("current_tools")
    topics = _infer_topics_from_messages(state.messages)
    details["topics_asked_about"] = topics
    if topics:
        result["customer_intent"] = f"Asked about {', '.join(topics)}"
    if state.escalation_triggered:
        result["recommended_next_action"] = (
            f"Human team should review and respond directly. Escalation reason: {state.escalation_reason}."
        )
    elif topics:
        result["recommended_next_action"] = (
            f"Follow up with accurate information on {', '.join(topics)} using the collected qualification details."
        )

    formatted = _format_summary(result)
    _save_session_log(state, result)

    return {"raw": result, "formatted": formatted}


def get_qualification_status(qualification: dict) -> str:
    if qualification.get("qualification_complete"):
        return "complete"
    filled = sum(
        1
        for field in ("business_type", "team_size", "current_tools")
        if qualification.get(field)
    )
    return "partial" if filled > 0 else "not_started"


def _normalise_sentiment(value: Optional[str], state: ConversationState) -> str:
    if value in {"positive", "neutral", "negative"}:
        return value

    if state.escalation_reason in {"COMPLAINT", "ANGRY_SENTIMENT"}:
        return "negative"

    user_text = " ".join(
        str(message.get("content", "")).lower()
        for message in state.messages
        if message.get("role") == "user"
    )
    negative_markers = {"unhappy", "pathetic", "angry", "frustrated", "unacceptable", "complaint"}
    return "negative" if any(marker in user_text for marker in negative_markers) else "neutral"


def _infer_topics_from_messages(messages: list) -> list:
    user_text = " ".join(
        str(message.get("content", "")).lower()
        for message in messages
        if message.get("role") == "user"
    )
    topics = []
    has_botox_medical_question = any(
        marker in user_text
        for marker in {"pregnant", "pregnancy", "allergic", "allergy", "medical", "safe"}
    ) and "botox" in user_text
    if has_botox_medical_question:
        topics.append("Medical Botox suitability")
    if "botox" in user_text and ("area" in user_text or "areas" in user_text):
        topics.append("Botox treatment areas")
    if "botox" in user_text and any(
        marker in user_text for marker in {"price", "prices", "pricing", "cost", "how much", "£"}
    ):
        topics.append("Botox pricing")
    if "filler" in user_text or "fillers" in user_text:
        topics.append("Dermal fillers pricing")
    if "consultation" in user_text or "consultations" in user_text:
        topics.append("Initial consultation")
    if "hour" in user_text or "open" in user_text or "closed" in user_text:
        topics.append("Opening hours")
    if "book" in user_text or "appointment" in user_text or "cancel" in user_text or "reschedul" in user_text:
        topics.append("Booking process")
    return topics


def _format_summary(summary: dict) -> str:
    lines = [
        "========================================",
        "        SESSION SUMMARY - CLOSIRA       ",
        "========================================",
        "",
        f"Customer intent:      {summary.get('customer_intent', 'N/A')}",
        f"Overall sentiment:    {summary.get('sentiment_overall', 'N/A')}",
        f"Qualification status: {summary.get('qualification_status', 'N/A')}",
        "",
        "-- Lead details collected --------------",
    ]
    details = summary.get("key_details_collected", {})
    lines.append(f"  Business type:   {details.get('business_type') or 'Not collected'}")
    lines.append(f"  Team size:       {details.get('team_size') or 'Not collected'}")
    lines.append(f"  Current tools:   {details.get('current_tools') or 'Not collected'}")
    topics = details.get("topics_asked_about", [])
    lines.append(f"  Topics covered:  {', '.join(topics) if topics else 'None'}")
    lines.append("")
    lines.append("-- SOP gaps (questions AI could not answer) --")
    gaps = summary.get("sop_gaps", [])
    if gaps:
        for g in gaps:
            lines.append(f"  - {g}")
    else:
        lines.append("  None - SOP was sufficient")
    lines.append("")
    esc = summary.get("escalation", {})
    lines.append("-- Escalation --------------------------")
    lines.append(f"  Triggered: {esc.get('triggered', False)}")
    if esc.get("triggered"):
        lines.append(f"  Reason:    {esc.get('reason', 'N/A')}")
        lines.append(f"  Time:      {esc.get('timestamp', 'N/A')}")
    lines.append("")
    lines.append("-- Recommended next action -------------")
    lines.append(f"  {summary.get('recommended_next_action', 'N/A')}")
    return "\n".join(lines)


def _save_session_log(state: ConversationState, summary: dict):
    log_dir = Path(__file__).resolve().parents[1] / "logs"
    os.makedirs(log_dir, exist_ok=True)
    log = {
        "session_id": state.session_id,
        "started_at": state.started_at,
        "turn_count": state.turn_count,
        "messages": state.messages,
        "qualification": state.qualification,
        "escalation_triggered": state.escalation_triggered,
        "escalation_reason": state.escalation_reason,
        "sop_gaps": state.sop_gaps,
        "summary": summary
    }
    with open(log_dir / f"session_{state.session_id}.json", "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2)
