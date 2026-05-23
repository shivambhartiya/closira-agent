from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class ConversationState:
    session_id: str
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    messages: list = field(default_factory=list)
    stage: str = "faq"  # faq | qualification | escalated | ended

    qualification: dict = field(default_factory=lambda: {
        "business_type": None,
        "team_size": None,
        "current_tools": None,
        "qualification_complete": False,
        "qualification_summary": None
    })

    escalation_triggered: bool = False
    escalation_reason: Optional[str] = None
    escalation_timestamp: Optional[str] = None

    sop_gaps: list = field(default_factory=list)
    turn_count: int = 0
    unanswered_count: int = 0
