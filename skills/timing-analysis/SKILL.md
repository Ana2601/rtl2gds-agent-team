---
name: timing-analysis
description: How the Timing agent reads OpenSTA results after placement or routing, diagnoses the critical path (logic- vs wire-dominated, setup vs hold), and routes the fix to the right agent. Use after every PD run.
---

# Timing analysis and fix routing

## Read the numbers that matter

- **WNS / TNS (setup)** at the spec clock, after detailed routing with parasitics.
  Pre-route numbers are estimates.
- **Hold WNS**. Hold is fixed in PD (`repair_timing -hold`), never in RTL.
- **The critical path** (`report_checks -path_delay max -fields {fanout cap slew}`):
  - startpoint and endpoint (which registers);
  - the number of logic levels;
  - **cell delay vs net delay**: sum the "delay" of the cell arcs (output pins) and of
    the net arcs (input pins) separately.

## Diagnose

| Pattern | Diagnosis | Send to |
|---|---|---|
| Cell delay ≥ 70 % of the data-path delay over 6 or more levels | Logic-dominated: too much logic between two registers | RTL agent: add a pipeline stage (if the latency budget allows), naming the start and end registers |
| Net delay is a large share, few levels, high fanout or long nets | Wire- or placement-dominated | PD agent: lower placement density / utilisation, let `repair_timing` buffer |
| Violation under about 5 % of the period | Optimisation-level | PD agent first, **once** (repair and resizing are cheap). If PD's attempt does not close it, RTL. Don't spend runs on density when the path is all cell delay |
| Hold violation | Clock-skew or short path | PD agent |

## Closure

Timing is closed when setup WNS ≥ 0 **and** hold WNS ≥ 0 after detailed routing at
the spec clock. Also report the slack margin. A design that closes with 1 % slack is
fragile: say so.

Never close timing by changing the clock, the I/O constraints or the corner. Those
belong to the spec. If the RTL agent has used up its latency budget and the path is
still logic-dominated, tell the orchestrator that the target is infeasible, with the
stage delays as evidence.

## A note on sky130hd blocks of this size

After routing, OpenROAD reports net (interconnect) delays near 0 ps on the critical
paths of a small block: wire load shows up as extra *cell* delay through the output
capacitance. So "100 % cell delay" is normal here. Fanout and capacitance are the wire
signal. Lowering placement density does not shorten a multiplier.
