# Test Transcript - Escalation Trigger

**Scenario:** Customer says, "i had your previous service it was pathetic."
**Expected behaviour:** The pre-filter detects a complaint immediately and Sophia hands off to a human with a logged reason.
**Stage(s) exercised:** Escalation Detection, Conversation Summary

---

**You:** i had your previous service it was pathetic

**Sophia:** I completely understand, and I want to make sure you get the best help possible. I'm passing you over to one of our team members right now who can assist you directly. [ESCALATED - Reason: COMPLAINT]

**Sophia:**

```text
========================================
        SESSION SUMMARY - CLOSIRA
========================================

Customer intent:      Expressing dissatisfaction with a previous service
Overall sentiment:    negative
Qualification status: not_started

-- Lead details collected --------------
  Business type:   Not collected
  Team size:       Not collected
  Current tools:   Not collected
  Topics covered:  None

-- SOP gaps (questions AI could not answer) --
  None - SOP was sufficient

-- Escalation --------------------------
  Triggered: True
  Reason:    COMPLAINT
  Time:      2026-05-23T14:40:53.947267

-- Recommended next action -------------
  Human team should review and respond directly. Escalation reason: COMPLAINT.
```

---

**Result:** Pass
**Escalation triggered:** Yes
**Reason logged:** COMPLAINT
**SOP gaps recorded:** None
