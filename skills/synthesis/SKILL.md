---
name: synthesis
description: How the Synthesis agent runs and judges logic synthesis (Yosys + ABC inside OpenROAD-flow-scripts on sky130hd) - constraints, what to check in the reports, and when to push back. Use for every verified RTL drop.
---

# Synthesis on sky130hd (OpenROAD-flow-scripts)

## Inputs

- The verified RTL, and the SDC: `create_clock` on the clock port at the spec period,
  plus input and output delays. The I/O constraints are part of the timing contract,
  so never drop them to make timing pass.
- ORFS knobs this agent owns:
  - `ABC_AREA`: 0 for delay-oriented mapping (the default when the clock is tight),
    1 for area-oriented;
  - `SYNTH_HIERARCHICAL`: flatten small blocks.

## What to check in the synthesis report

| Check | Why |
|---|---|
| No latches (`$_DLATCH_` / `dlxtp` cells) | An unintended latch is an RTL bug. Send it back to RTL |
| Flop count matches the architecture | Every intended pipeline register exists, and nothing was optimised away by mistake |
| Cell area | The baseline for PD's utilisation choice. Big jumps between versions need an explanation |
| No unmapped or blackbox cells | Otherwise the flow will fail later |

## Hand-off

Send PD the netlist's cell area and the flop count. If the Timing agent reports a
small, logic-dominated violation and the RTL cannot change, re-synthesise with
`ABC_AREA=0` before asking for pipelining.
