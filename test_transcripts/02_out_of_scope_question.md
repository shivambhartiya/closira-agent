# Test Transcript - Out-of-Scope Question

**Scenario:** Customer asks about laser hair removal, then parking. A third planned gap question about teeth whitening is not reached because escalation triggers at the SOP-gap threshold.
**Expected behaviour:** Sophia acknowledges each gap politely without guessing. After the second unanswered question, escalation is triggered automatically.
**Stage(s) exercised:** FAQ Answering, Escalation Detection, Conversation Summary

---

**You:** Do you offer laser hair removal?

**Sophia:** That's a great question - let me get that confirmed for you by a member of our team.

**You:** Do you have parking?

**Sophia:** I want to make sure you get accurate answers to all your questions. Let me connect you with a member of our team who can help you fully. [ESCALATED - Reason: SOP gap threshold reached - 2 consecutive unanswered questions]

**Sophia:**

```text
========================================
        SESSION SUMMARY - CLOSIRA
========================================

Customer intent:      Inquire about services and facilities offered by Bloom Aesthetics Clinic
Overall sentiment:    neutral
Qualification status: not_started

-- Lead details collected --------------
  Business type:   Not collected
  Team size:       Not collected
  Current tools:   Not collected
  Topics covered:  None

-- SOP gaps (questions AI could not answer) --
  - laser hair removal
  - parking

-- Escalation --------------------------
  Triggered: True
  Reason:    SOP gap threshold reached - 2 consecutive unanswered questions
  Time:      2026-05-23T14:53:45.614660

-- Recommended next action -------------
  Human team should review and respond directly. Escalation reason: SOP gap threshold reached - 2 consecutive unanswered questions.
```

---

**Result:** Pass
**Escalation triggered:** Yes
**Reason logged:** SOP gap threshold reached - 2 consecutive unanswered questions
**SOP gaps recorded:** laser hair removal, parking
