---
name: verification
description: How the Verification agent signs off RTL before it may be synthesised - golden model from the spec, vector selection, cycle-exact checking, and what to send back to the RTL agent. Use whenever RTL is new or changed.
---

# Verification sign-off for an RTL drop

1. **Golden model from the spec, never from the RTL.** For `dot4`: the result of
   the operands of cycle t appears at t + 1 + L. A reset anywhere in between flushes
   it. `y` is don't-care while `out_valid` is low.
2. **Vectors:**
   - random operands, with about 30 % of lanes drawn from the corner set
     {-128, 127, 0, -1, 1};
   - all-extreme operand sets (−128 × −128 on every lane is the maximum result,
     65,536, which needs the 18th bit);
   - `in_valid` gaps of about 20 %;
   - reset pulses in the middle of traffic.
3. **Check every cycle:**
   - `out_valid` against the model, in every cycle;
   - `y` only when the model says a result is due.

   Also check that the latency the RTL agent claims matches the observed one. A
   design that is right, but at a different latency, is wrong.
4. **Lint is part of sign-off:** `verilator -Wall` must be clean.
5. **Report back:**
   - Pass: tell the Synthesis agent, with the RTL file and the verified latency.
   - Fail: tell the RTL agent the first mismatches (cycle, expected, observed). Do not
     guess the fix.

Any RTL change, however small, invalidates the previous sign-off.
