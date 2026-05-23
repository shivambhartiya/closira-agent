"""
Closira AI Customer Support Agent - CLI
Usage: python main.py
Type 'quit', 'bye', 'exit', 'done', or 'summary' to end the session.
"""

import os
import re
import sys
import uuid

from dotenv import load_dotenv

from agent.state import ConversationState
from agent.sop import load_sop, sop_to_text
from agent.stages import begin_qualification_prompt, handle_faq, handle_qualification
from agent.escalation import (
    check_escalation,
    create_llm_client,
    normalise_escalation_reason,
    trigger_escalation,
)
from agent.summariser import generate_summary

load_dotenv()

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

EXIT_WORDS = {"quit", "exit", "bye", "goodbye", "done", "summary", "end"}

# After this many FAQ turns, move to qualification stage.
FAQ_TURNS_BEFORE_QUALIFICATION = 2


def _contains_escalation_intent(text: str) -> bool:
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in {
            "human",
            "real person",
            "manager",
            "complaint",
            "unhappy",
            "angry",
            "frustrated",
            "unacceptable",
            "medical",
            "allergic",
            "allergy",
            "pregnant",
            "discount",
            "cheaper",
        }
    )


def _is_plain_pricing_enquiry(text: str) -> bool:
    lowered = text.lower()
    pricing_words = {"price", "prices", "pricing", "cost", "costs", "how much"}
    service_words = {"botox", "filler", "fillers", "consultation", "consultations", "unit", "units"}
    negotiation_words = {"discount", "cheaper", "negotiate", "haggle", "too expensive", "lower price"}
    return (
        any(word in lowered for word in pricing_words)
        and any(word in lowered for word in service_words)
        and not any(word in lowered for word in negotiation_words)
    )


def _is_exit_message(text: str) -> bool:
    lowered = text.strip().lower()
    if lowered in EXIT_WORDS:
        return True
    return any(re.search(rf"\b{re.escape(word)}\b", lowered) for word in EXIT_WORDS)


def _is_booking_enquiry(text: str) -> bool:
    lowered = text.lower()
    booking_words = {"book", "booking", "appointment", "schedule", "reserve"}
    human_words = {"human", "real person", "manager", "agent", "someone", "staff member"}
    has_booking_intent = any(
        re.search(rf"\b{re.escape(word)}\b", lowered) for word in booking_words
    )
    has_human_request = any(
        re.search(rf"\b{re.escape(phrase)}\b", lowered) for phrase in human_words
    )
    return has_booking_intent and not has_human_request


def _is_routine_sop_enquiry(text: str) -> bool:
    lowered = text.lower()
    routine_markers = {
        "service",
        "services",
        "botox",
        "filler",
        "fillers",
        "consultation",
        "consultations",
        "hour",
        "hours",
        "open",
        "closed",
        "book",
        "booking",
        "appointment",
        "cancellation",
        "cancel",
        "reschedule",
        "policy",
    }
    return any(re.search(rf"\b{re.escape(marker)}\b", lowered) for marker in routine_markers)


def _is_known_sop_gap_enquiry(text: str) -> bool:
    lowered = text.lower()
    return any(
        marker in lowered
        for marker in {
            "laser",
            "hair removal",
            "parking",
            "teeth whitening",
            "tooth whitening",
            "whitening",
        }
    )


def _looks_like_qualification_answer(state: ConversationState, text: str) -> bool:
    if state.stage != "qualification":
        return False

    cleaned = text.strip().lower()
    if not cleaned or "?" in cleaned or _contains_escalation_intent(cleaned):
        return False

    if state.qualification.get("business_type") is None:
        return len(cleaned.split()) <= 8

    if state.qualification.get("team_size") is None:
        return any(char.isdigit() for char in cleaned) or any(
            word in cleaned
            for word in {"team", "people", "staff", "employees", "solo", "alone", "just me"}
        )

    if state.qualification.get("current_tools") is None:
        return any(
            word in cleaned
            for word in {
                "whatsapp",
                "email",
                "phone",
                "website",
                "crm",
                "zendesk",
                "intercom",
                "hubspot",
                "excel",
                "sheets",
                "insta",
                "instagram",
                "ig",
                "dm",
                "dms",
                "slack",
                "messenger",
            }
        )

    return False


def _print_and_store_assistant_message(state: ConversationState, text: str) -> None:
    print(f"\nSophia: {text}\n")
    state.messages.append({"role": "assistant", "content": text})


def _generate_and_print_summary(client, state: ConversationState, sop_text: str) -> None:
    print("[Session escalated. Generating summary...]\n" if state.escalation_triggered else "")
    summary = generate_summary(client, state, sop_text)
    print(summary["formatted"])
    print(f"\n[Full session log saved -> logs/session_{state.session_id}.json]\n")


def run():
    try:
        client = create_llm_client()
    except ValueError as exc:
        print(f"ERROR: {exc}")
        print("Copy .env.example to .env and configure your provider, model, and API key.")
        return

    sop = load_sop()
    sop_text = sop_to_text(sop)
    state = ConversationState(session_id=str(uuid.uuid4())[:8])

    print("\n" + "=" * 50)
    print("  Bloom Aesthetics Clinic - Customer Support")
    print("  Powered by Closira AI")
    print(f"  Model backend: {client.provider} / {client.model}")
    print("=" * 50)
    print("  Type 'bye' or 'quit' at any time to end the session.")
    print("=" * 50 + "\n")

    # Opening message - no API call needed.
    opening = (
        "Hello! Welcome to Bloom Aesthetics Clinic. "
        "I'm Sophia, and I'm here to help you today. "
        "How can I assist you?"
    )
    print(f"Sophia: {opening}\n")
    state.messages.append({"role": "assistant", "content": opening})

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n[Session interrupted.]\n")
            break

        if not user_input:
            continue

        if _is_exit_message(user_input):
            print("\n[Generating session summary - please wait...]\n")
            summary = generate_summary(client, state, sop_text)
            print(summary["formatted"])
            print(f"\n[Full session log saved -> logs/session_{state.session_id}.json]\n")
            break

        state.turn_count += 1
        state.messages.append({"role": "user", "content": user_input})

        # Layer 1 escalation pre-check. Simple qualification answers are allowed
        # through so short answers like "5", "tech", or "insta" are not misread
        # as out-of-scope messages.
        if not _looks_like_qualification_answer(state, user_input):
            esc_check = check_escalation(client, state, user_input, sop_text)
            if esc_check.get("should_escalate"):
                raw_reason = esc_check.get("trigger") or esc_check.get("reasoning") or "unspecified trigger"
                reason = normalise_escalation_reason(raw_reason)
                if reason in {"PRICING_NEGOTIATION", "OUT_OF_SCOPE"} and _is_plain_pricing_enquiry(user_input):
                    reason = None
                    esc_check["should_escalate"] = False
                if reason in {"EXPLICIT_ESCALATION", "EXPLICIT_REQUEST_FOR_HUMAN_AGENT", "OUT_OF_SCOPE"} and _is_booking_enquiry(user_input):
                    reason = None
                    esc_check["should_escalate"] = False
                if reason in {"EXPLICIT_ESCALATION", "OUT_OF_SCOPE"} and _is_routine_sop_enquiry(user_input):
                    reason = None
                    esc_check["should_escalate"] = False
                if reason == "OUT_OF_SCOPE" and _is_known_sop_gap_enquiry(user_input):
                    reason = None
                    esc_check["should_escalate"] = False
                if not esc_check.get("should_escalate"):
                    pass
                else:
                    if reason == "OUT_OF_SCOPE":
                        state.sop_gaps.append("out-of-scope question")
                    response_text = trigger_escalation(state, reason)
                    _print_and_store_assistant_message(state, response_text)
                    _generate_and_print_summary(client, state, sop_text)
                    break

        # Stage routing.
        if state.stage == "escalated":
            print("Sophia: You've been connected to our team. Please hold.\n")
            break

        if state.stage == "qualification":
            result = handle_qualification(client, state, user_input, sop_text)
        else:
            result = handle_faq(client, state, user_input, sop_text)

            if (
                state.turn_count >= FAQ_TURNS_BEFORE_QUALIFICATION
                and state.stage == "faq"
                and not state.escalation_triggered
            ):
                state.stage = "qualification"
                if result.get("can_answer", True):
                    result["reply"] = (
                        f"{result.get('reply', '').strip()}\n\n"
                        f"{begin_qualification_prompt(state)}"
                    ).strip()

        # Escalation triggered inside a stage handler.
        if state.escalation_triggered:
            response_text = result.get("reply", "Let me connect you with our team.")
            _print_and_store_assistant_message(state, response_text)
            _generate_and_print_summary(client, state, sop_text)
            break

        response_text = result.get("reply", "I'm sorry, I didn't quite catch that. Could you rephrase?")
        _print_and_store_assistant_message(state, response_text)


if __name__ == "__main__":
    run()
