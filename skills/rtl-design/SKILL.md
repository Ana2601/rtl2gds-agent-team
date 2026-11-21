---
name: rtl-design
description: How the RTL agent writes and revises synthesisable SystemVerilog for a block with a timing target, and how it responds to timing feedback (pipelining within a latency budget). Use when creating RTL from a spec or changing RTL after a timing or verification issue.
---

# RTL design for a timing target

## Writing the first version

- Read the spec's interface, its latency rule and its sign-off targets first.
- **Start from the minimum latency the spec allows.** Extra registers cost area and
  latency. Add them only when timing proves they are needed.
- Register the inputs and the outputs when the spec says the block sits between
  synchronous blocks, so its timing is self-contained.
- Reset only control state (valid pipelines, FSMs, counters). Datapath registers whose
  contents are don't-care until `valid` don't need a reset; that saves area and reset
  fan-out.
- Signed arithmetic: extend the operands to the result width before the operator
  (`16'(a) * 16'(b)` with signed `a`, `b`).
- Sum many terms as a **balanced tree**, not a chain. Synthesis rebuilds `+` chains
  inside one expression, but not across separate statements.

## Responding to the Timing agent

| Timing finding | RTL response |
|---|---|
| Setup violation, **logic-dominated** (the path's cell delay is most of the period: many logic levels through a multiplier or adder tree) | Add one pipeline stage at the cut that splits the critical path most evenly, if the latency budget allows. Typical order of cuts for a multiply-accumulate: after the products, then after the first adder level, then inside the multiplier (partial-product rows) |
| Violation **wire- or placement-dominated** (few levels, large net delay) | Not an RTL problem. Leave it to PD |
| Latency budget exhausted and still logic-dominated | Report to the orchestrator that the clock target is infeasible for this micro-architecture, with the stage delays. Do not change the clock yourself |

Every RTL change goes back to the Verification agent before synthesis. A pipeline
change changes the latency, so tell the Verification agent the new latency.

## Checks before handing off

- `verilator --lint-only -Wall` is clean, with no waivers.
- No latches, no combinational loops, no `initial` blocks in synthesisable code.
