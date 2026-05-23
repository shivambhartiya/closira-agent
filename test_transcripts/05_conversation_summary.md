---
# Test Transcript - Conversation Summary

**Scenario:** A full multi-turn session covering FAQ, lead qualification, a mid-qualification pricing enquiry, and customer exit.
**Expected behaviour:** The CLI prints the formatted session summary with customer intent, collected details, SOP gaps, escalation status, and recommended next action.
**Stage(s) exercised:** FAQ Answering, Lead Qualification, Conversation Summary

---

**You:** What are your Botox prices?

**Sophia:** Botox starts from £200, and the exact price depends on the area and units required.

**You:** Do you offer free consultations?

**Sophia:** Initial consultations are free of charge and come with no obligation.

Before you go, may I ask what type of business or industry you're in?

**You:** What are your opening hours?

**Sophia:** Bloom Aesthetics Clinic is open Monday to Saturday, 9:00 AM to 7:00 PM, and closed on Sundays.

**You:** i would like to know the cost of 12 unit botox

**Sophia:** Botox starts from £200. The exact price depends on the area and units required, so I can't calculate a specific 12-unit total from the SOP.

Before you go, may I ask what type of business or industry you're in?

**You:** tech

**Sophia:** Thank you. Roughly how many people are on your team?

**You:** 5

**Sophia:** Thank you. What tools do you currently use for customer communications?

**You:** insta

**Sophia:** Thank you - I have everything I need for the qualification notes. All qualification fields were collected successfully.

**You:** bye

**Sophia:**

```text
========================================
        SESSION SUMMARY - CLOSIRA
========================================

Customer intent:      Asked about Botox pricing, Initial consultation, Opening hours
Overall sentiment:    neutral
Qualification status: complete

-- Lead details collected --------------
  Business type:   tech
  Team size:       5
  Current tools:   insta
  Topics covered:  Botox pricing, Initial consultation, Opening hours

-- SOP gaps (questions AI could not answer) --
  None - SOP was sufficient

-- Escalation --------------------------
  Triggered: False

-- Recommended next action -------------
  Follow up with accurate information on Botox pricing, Initial consultation, Opening hours using the collected qualification details.
```

---

**Result:** Pass  
**Escalation triggered:** No  
**Reason logged:** N/A  
**SOP gaps recorded:** None

---
