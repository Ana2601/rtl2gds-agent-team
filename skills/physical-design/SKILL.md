---
name: physical-design
description: How the PD agent takes a synthesised netlist to a DRC-clean routed layout and GDS with OpenROAD (floorplan, placement, CTS, global and detailed routing) and which knobs to turn when routing or timing fails. Use for every netlist the Synthesis agent hands over.
---

# Physical design with OpenROAD (sky130hd)

## Flow and what each stage gives you

| Stage | OpenROAD steps | Look at |
|---|---|---|
| Floorplan | `initialize_floorplan` (utilisation, aspect ratio), I/O pins, tapcells, PDN | core area, utilisation |
| Placement | global placement (`gpl`, density target), resizing, detailed placement | overflow, displacement, estimated WNS |
| CTS | `clock_tree_synthesis`, then `repair_timing` for hold | clock skew, hold WNS |
| Global route | `global_route` with congestion-driven layer assignment | congestion overflow |
| Detailed route | TritonRoute | **DRC count, which must be 0** |
| Finish | fill, final STA and GDS | WNS/TNS (setup), hold WNS, GDS |

## Knobs and when to use them

| Symptom | Action |
|---|---|
| Global or detailed routing congestion, DRCs that don't converge | Lower `CORE_UTILIZATION` by about 10 points, or lower `PLACE_DENSITY`. Routing resources grow with area |
| Small setup violation with wire- or placement-dominated paths | Lower `PLACE_DENSITY` (shorter detours), and let `repair_timing` resize and buffer |
| Hold violations after CTS | Handled by `repair_timing -hold` in the flow. If any remain, report them; never fix hold by slowing the clock |
| Logic-dominated setup violation | Not a PD problem. Hand it to the Timing agent for RTL |

## Starting point for a small datapath block

`CORE_UTILIZATION = 50`, `PLACE_DENSITY = 0.65`, square aspect ratio. Moving from 50 %
to 60 % saves area if routing stays DRC-clean, so tighten only after closure.

## Sign-off you report

Routed DRC count, antenna violations, core area, utilisation, setup and hold WNS/TNS,
total power, and the GDS path.
