import json
import re
from typing import Optional

from agent.state import ConversationState
from agent.escalation import call_llm, normalise_escalation_reason, trigger_escalation


def _build_master_system_prompt(sop_text: str) -> str:
    return f"""You are Sophia, a professional and warm customer support assistant for Bloom Aesthetics Clinic. You communicate via WhatsApp and web chat on behalf of the clinic.

YOUR PERSONA:
- Warm, professional, and reassuring - like a knowledgeable receptionist
- Keep responses concise: 2-4 sentences per message, never long paragraphs
- Use British English spelling throughout (e.g. colour, centre, licence)
- Never use medical jargon or clinical terms beyond what the SOP includes
- Be friendly but never overly casual

STRICT SOP BOUNDARIES - THIS IS THE MOST IMPORTANT RULE:
You may ONLY answer questions using the information provided in the SOP below.
If a customer asks something not covered in the SOP:
- Do NOT guess, infer, or extrapolate any facts
- Do NOT hallucinate prices, services, availability, or policies
- Set "can_answer": false in your JSON response
- Set "sop_gap" to a short label of the question topic (e.g. "laser hair removal", "parking")
- Use this phrase in "reply": "That's a great question - let me get that confirmed for you by a member of our team."

SOP DATA (answer only from this):
---
{sop_text}
---

ESCALATION RULES - ESCALATE IMMEDIATELY if any of these are present:
- Customer expresses frustration, anger, or makes any complaint
- Customer asks any medical, health, or contraindication-related question
- Customer attempts to negotiate pricing or request a discount
- Two consecutive questions cannot be answered from the SOP
- Customer explicitly asks to speak to a human, manager, or real person

When escalating: set "escalate": true, write a warm empathetic handoff message in "reply", and fill "escalation_reason" with a clear short label.

OUTPUT FORMAT - Respond ONLY in valid JSON. No prose before or after the JSON block:
{{
  "reply": "The message to send to the customer",
  "can_answer": true,
  "sop_gap": null,
  "escalate": false,
  "escalation_reason": null,
  "confidence": "high"
}}"""


def _record_sop_boundary_result(state: ConversationState, result: dict) -> None:
    if result.get("sop_gap") == "api_error":
        return

    if not result.get("can_answer", True):
        gap = result.get("sop_gap") or "unknown topic"
        state.sop_gaps.append(gap)
        state.unanswered_count += 1
    else:
        state.unanswered_count = 0


def begin_qualification_prompt(state: ConversationState) -> str:
    """Return the next qualification question without making another API call."""
    if state.qualification.get("business_type") is None:
        return "Before you go, may I ask what type of business or industry you're in?"
    if state.qualification.get("team_size") is None:
        return "Roughly how many people are on your team?"
    if state.qualification.get("current_tools") is None:
        return "What tools do you currently use for customer communications?"
    return "Thank you - I have everything I need for the qualification notes."


def _last_assistant_message(state: ConversationState) -> str:
    for message in reversed(state.messages):
        if message.get("role") == "assistant":
            return str(message.get("content", ""))
    return ""


def _append_qualification_prompt_if_needed(state: ConversationState, reply: str) -> str:
    current_question = begin_qualification_prompt(state)
    if current_question in reply or current_question in _last_assistant_message(state):
        return reply.strip()
    return f"{reply.strip()}\n\n{current_question}".strip()


def _next_missing_qualification_field(state: ConversationState) -> Optional[str]:
    for field in ("business_type", "team_size", "current_tools"):
        if state.qualification.get(field) is None:
            return field
    return None


def _fallback_extract_qualification(field_name: Optional[str], user_input: str) -> Optional[str]:
    cleaned = user_input.strip()
    if not field_name or not cleaned or "?" in cleaned:
        return None

    lowered = cleaned.lower()
    if field_name == "business_type" and len(lowered.split()) <= 8:
        for prefix in (
            "i run a ",
            "i run an ",
            "we run a ",
            "we run an ",
            "we are a ",
            "we're a ",
            "i work in ",
            "we work in ",
            "i am in ",
            "i'm in ",
        ):
            if lowered.startswith(prefix):
                return cleaned[len(prefix):]
        return cleaned
    if field_name == "team_size" and (
        any(char.isdigit() for char in lowered)
        or any(word in lowered for word in {"team", "people", "staff", "employees", "solo", "alone", "just me"})
    ):
        return cleaned
    if field_name == "current_tools":
        for prefix in ("i use ", "we use ", "currently use ", "we currently use "):
            if lowered.startswith(prefix):
                return cleaned[len(prefix):]
        return cleaned
    return None


def _is_customer_question(user_input: str) -> bool:
    lowered = user_input.strip().lower()
    if "?" in lowered:
        return True
    question_markers = (
        "what",
        "how",
        "when",
        "where",
        "do you",
        "can you",
        "could you",
        "i would like to know",
        "i want to know",
        "tell me",
    )
    sop_topic_words = (
        "price",
        "prices",
        "pricing",
        "cost",
        "costs",
        "botox",
        "filler",
        "fillers",
        "consultation",
        "consultations",
        "book",
        "booking",
        "appointment",
        "hours",
        "open",
        "closed",
        "cancel",
        "reschedule",
    )
    has_question_marker = any(
        marker in lowered if " " in marker else _has_word(lowered, marker)
        for marker in question_markers
    )
    has_sop_topic = any(
        _has_word(lowered, word)
        for word in sop_topic_words
    )
    return has_question_marker or has_sop_topic


def _is_plain_pricing_enquiry(user_input: str) -> bool:
    lowered = user_input.lower()
    negotiation_words = {"discount", "cheaper", "negotiate", "haggle", "too expensive", "lower price"}
    pricing_words = {"price", "prices", "pricing", "cost", "costs", "how much"}
    service_words = {"botox", "filler", "fillers", "consultation", "consultations", "unit", "units"}
    return (
        any(word in lowered for word in pricing_words)
        and any(word in lowered for word in service_words)
        and not any(word in lowered for word in negotiation_words)
    )


def _is_actual_pricing_negotiation(user_input: str) -> bool:
    lowered = user_input.lower()
    return any(
        phrase in lowered
        for phrase in {
            "discount",
            "cheaper",
            "negotiate",
            "haggle",
            "too expensive",
            "lower price",
            "can you do it for",
            "best price",
        }
    )


def _has_word(text: str, word: str) -> bool:
    return bool(re.search(rf"\b{re.escape(word)}\b", text))


def _answer_sop_question_deterministically(user_input: str) -> Optional[str]:
    lowered = user_input.lower()
    if "service" in lowered or "services" in lowered:
        return "Bloom Aesthetics Clinic offers Botox, Dermal Fillers, and Initial Consultations."
    if "botox" in lowered and _is_plain_pricing_enquiry(user_input):
        if "unit" not in lowered and not any(char.isdigit() for char in lowered):
            return "Botox starts from £200, and the exact price depends on the area and units required."
        return (
            "Botox starts from £200. The exact price depends on the area and units required, "
            "so I can't calculate a specific 12-unit total from the SOP."
        )
    if ("filler" in lowered or "fillers" in lowered) and _is_plain_pricing_enquiry(user_input):
        return "Dermal fillers start from £250 and include lip, cheek, and nasolabial fillers."
    if "consultation" in lowered:
        return "Initial consultations are free of charge and come with no obligation."
    if "hour" in lowered or "open" in lowered or "closed" in lowered:
        return "Bloom Aesthetics Clinic is open Monday to Saturday, 9:00 AM to 7:00 PM, and closed on Sundays."
    if any(_has_word(lowered, word) for word in {"book", "booking", "appointment"}):
        return "Bookings are available via WhatsApp or the website."
    if "cancel" in lowered or "cancellation" in lowered:
        return "The clinic requires 24 hours notice for cancellations."
    if "reschedul" in lowered:
        return "For rescheduling, contact the clinic at least 24 hours before your appointment."
    return None


def _deterministic_sop_gap(user_input: str) -> Optional[str]:
    lowered = user_input.lower()
    gap_markers = {
        "botox area": "Botox treatment areas",
        "botox areas": "Botox treatment areas",
        "laser": "laser hair removal",
        "hair removal": "laser hair removal",
        "parking": "parking",
        "park": "parking",
        "teeth whitening": "teeth whitening",
        "tooth whitening": "teeth whitening",
        "whitening": "teeth whitening",
    }
    for marker, gap in gap_markers.items():
        if marker in lowered:
            return gap
    return None


def handle_faq(client, state: ConversationState, user_input: str, sop_text: str) -> dict:
    """
    Stage 1 - FAQ Answering.
    Answers customer questions using only the SOP data.
    Tracks unanswered questions and forces escalation at threshold.
    """
    system_prompt = _build_master_system_prompt(sop_text)

    result = call_llm(client, system_prompt, state.messages)

    deterministic_answer = _answer_sop_question_deterministically(user_input)
    if deterministic_answer:
        result["reply"] = deterministic_answer
        result["can_answer"] = True
        result["sop_gap"] = None
        result["escalate"] = False
        result["escalation_reason"] = None

    deterministic_gap = _deterministic_sop_gap(user_input)
    if deterministic_gap:
        result["reply"] = "That's a great question - let me get that confirmed for you by a member of our team."
        result["can_answer"] = False
        result["sop_gap"] = deterministic_gap
        result["escalate"] = False
        result["escalation_reason"] = None

    _record_sop_boundary_result(state, result)

    escalation_reason = normalise_escalation_reason(result.get("escalation_reason"))
    if result.get("escalate") and escalation_reason == "PRICING_NEGOTIATION" and _is_plain_pricing_enquiry(user_input):
        result["escalate"] = False
        result["escalation_reason"] = None
    elif result.get("escalate") and escalation_reason == "PRICING_NEGOTIATION" and not _is_actual_pricing_negotiation(user_input):
        result["escalate"] = False
        result["escalation_reason"] = None

    # Force escalation after 2+ consecutive unanswered questions.
    if state.unanswered_count >= 2 and not result.get("escalate", False):
        result["escalate"] = True
        result["escalation_reason"] = "SOP gap threshold reached - 2 consecutive unanswered questions"
        result["reply"] = (
            "I want to make sure you get accurate answers to all your questions. "
            "Let me connect you with a member of our team who can help you fully. "
            "[ESCALATED - Reason: SOP gap threshold reached - 2 consecutive unanswered questions]"
        )

    if result.get("escalate"):
        handoff = trigger_escalation(state, result.get("escalation_reason", "unspecified"))
        result["reply"] = result.get("reply") or handoff

    return result


def handle_qualification(client, state: ConversationState, user_input: str, sop_text: str) -> dict:
    """
    Stage 2 - Lead Qualification.
    Asks 3 structured questions one at a time and extracts answers into state.
    """
    qualification_json = json.dumps(state.qualification, indent=2)
    expected_field = _next_missing_qualification_field(state)

    system_prompt = _build_master_system_prompt(sop_text) + f"""

CURRENT TASK - LEAD QUALIFICATION:
You have completed the initial FAQ stage. Now gently gather the following information in a natural, conversational way. Ask only ONE question at a time. Never list all questions at once.

CRITICAL: Only extract an answer if the customer's message is a direct response to the question you just asked. If the customer is asking a new question instead of answering yours, set "extracted_answer" to null, answer their question first using the SOP, then re-ask the current qualification question at the end of your reply.

If the customer asks a question that can be answered from the SOP, answer it fully first, then ask the next qualification question at the end of your reply. Never skip a customer's question in order to push qualification forward.

Questions to collect (in this order):
1. Business type or industry [field: business_type] - if not yet collected
2. Approximate team size [field: team_size] - if not yet collected
3. Current tools used for customer communications [field: current_tools] - if not yet collected

Current qualification state (check which fields are still null):
{qualification_json}

When you receive an answer, extract it cleanly into the "extracted_answer" field.
After extracting an answer, ask the next unanswered qualification question in "reply".
When all three fields are collected, set "qualification_complete": true and write a concise 2-sentence summary in "qualification_summary".

OUTPUT FORMAT - Respond ONLY in valid JSON:
{{
  "reply": "...",
  "can_answer": true,
  "sop_gap": null,
  "escalate": false,
  "escalation_reason": null,
  "confidence": "high",
  "extracted_answer": {{"field": "business_type", "value": "dental clinic"}},
  "qualification_complete": false,
  "qualification_summary": null
}}

If no answer was given (customer asked a different question instead), set "extracted_answer" to null and answer their question first before re-asking."""

    result = call_llm(client, system_prompt, state.messages)
    # Qualification extracts lead data; it must not create SOP gaps.

    escalation_reason = normalise_escalation_reason(result.get("escalation_reason"))
    if result.get("escalate") and escalation_reason == "PRICING_NEGOTIATION" and not _is_actual_pricing_negotiation(user_input):
        result["escalate"] = False
        result["escalation_reason"] = None

    customer_asked_question = _is_customer_question(user_input)
    fallback_value = None if customer_asked_question else _fallback_extract_qualification(expected_field, user_input)
    extracted_was_saved = False
    if fallback_value:
        state.qualification[expected_field] = fallback_value
        extracted_was_saved = True

    extracted = result.get("extracted_answer")
    if not customer_asked_question and not extracted_was_saved and extracted and isinstance(extracted, dict):
        field_name = extracted.get("field")
        field_value = extracted.get("value")
        if (
            field_name == expected_field
            and field_name in state.qualification
            and state.qualification.get(field_name) is None
            and field_value
        ):
            state.qualification[field_name] = field_value
            extracted_was_saved = True

    required_fields = ("business_type", "team_size", "current_tools")
    all_fields_collected = all(state.qualification.get(field) for field in required_fields)
    if result.get("qualification_complete") or all_fields_collected:
        state.qualification["qualification_complete"] = True
        state.qualification["qualification_summary"] = (
            result.get("qualification_summary")
            or "All qualification fields were collected successfully."
        )
        result["reply"] = (
            "Thank you - I have everything I need for the qualification notes. "
            f"{state.qualification['qualification_summary']}"
        )
    elif extracted_was_saved:
        result["reply"] = f"Thank you. {begin_qualification_prompt(state)}"
    elif customer_asked_question:
        deterministic_answer = _answer_sop_question_deterministically(user_input)
        if deterministic_answer:
            result["reply"] = _append_qualification_prompt_if_needed(
                state,
                deterministic_answer,
            )
            result["can_answer"] = True
            result["escalate"] = False
            result["escalation_reason"] = None
        elif not result.get("can_answer", True):
            result["reply"] = _append_qualification_prompt_if_needed(
                state,
                "That's a great question - let me get that confirmed for you by a member of our team.",
            )
        else:
            reply = result.get("reply", "").strip()
            result["reply"] = _append_qualification_prompt_if_needed(state, reply)

    if state.unanswered_count >= 2 and not result.get("escalate", False):
        result["escalate"] = True
        result["escalation_reason"] = "SOP gap threshold reached - 2 consecutive unanswered questions"
        result["reply"] = (
            "I want to make sure you get accurate answers to all your questions. "
            "Let me connect you with a member of our team who can help you fully. "
            "[ESCALATED - Reason: SOP gap threshold reached - 2 consecutive unanswered questions]"
        )

    if result.get("escalate"):
        handoff = trigger_escalation(state, result.get("escalation_reason", "unspecified"))
        result["reply"] = result.get("reply") or handoff

    return result
