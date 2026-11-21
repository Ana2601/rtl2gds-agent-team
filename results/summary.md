## Sign-off

| Item | Result |
|---|---|
| Architecture | latency 3, pipeline registers after: products, mult_mid |
| Clock | 4.0 ns (250 MHz), sky130hd typical |
| Setup WNS / TNS | +0.041 ns / 0.000 ns |
| Hold WNS | +0.067 ns |
| DRC / antenna | 0 / 0 |
| Core area / cell area | 28780 um² / 19566 um² (utilisation 68%) |
| Power (typical, default activity) | 8.168 mW |
| Verification | 4808 results over 6000 cycles, bit-exact |
| GDS | `signoff/dot4.gds` |

## Flow runs

| Run | Latency | Util / density | Place WNS | Routed WNS | Hold WNS | DRC | Core area | Worst path (levels, cell / net delay) |
|---:|---:|---|---:|---:|---:|---:|---:|---|
| 1 | 1 | 50 % / 0.65 | -2.284 | - | - | - | - | ar[2][7]$_DFFE_PP_ → y[17]$_DFF_P_ (15, 6.17 / 0.0 ns) |
| 2 | 2 | 50 % / 0.65 | -0.181 | -0.053 | +0.150 | 0 | 27026 | br[0][5]$_DFFE_PP_ → pq[0][15]$_DFF_P_ (12, 3.94 / 0.0 ns) |
| 3 | 2 | 40 % / 0.55 | -0.225 | - | - | - | - | ar[1][3]$_DFFE_PP_ → pq[1][14]$_DFF_P_ (12, 4.11 / 0.0 ns) |
| 4 | 3 | 50 % / 0.65 | +0.141 | +0.126 | +0.062 | 0 | 34543 | br[1][5]$_DFFE_PP_ → phi[1][11]$_DFF_P_ (11, 3.74 / 0.0 ns) |
| 5 | 3 | 60 % / 0.65 | +0.070 | +0.041 | +0.067 | 0 | 28780 | br[3][6]$_DFFE_PP_ → phi[3][11]$_DFF_P_ (11, 3.85 / 0.0 ns) |

## Team message log

| # | From | To | Kind | Message |
|---:|---|---|---|---|
| 1 | orchestrator | rtl | implement | implement dot4 per spec: clock 4.0 ns on sky130hd, sign-off = verified, setup/hold WNS >= 0, 0 DRC |
| 2 | rtl | verification | verify | latency 1, pipeline registers after: none; minimum latency the spec allows (L=1); pipeline only if timing proves it necessary. Lint clean. |
| 3 | verification | synthesis | synthesize | PASS: 6000 cycles, 4817 results bit-exact vs the golden model (latency 1, corner operands, mid-traffic resets) |
| 4 | synthesis | pd | implement | netlist: 834 cells, 12107 um2, 84 flops, no latches (ABC delay-oriented) |
| 5 | pd | timing | analyze | placed (floorplan + placement): util 50 %, density 0.65; estimated setup WNS -2.28 ns |
| 6 | timing | rtl | pipeline | WNS -2.284 ns at 4.0 ns; worst path ar[2][7]$_DFFE_PP_ -> y[17]$_DFF_P_: 15 levels, cell 6.17 ns / net 0.00 ns (100% cell). Logic-dominated; 57% of the period, not worth routing: needs a register stage. |
| 7 | rtl | verification | verify | latency 2, pipeline registers after: products; timing reports a logic-dominated path ar[2][7]$_DFFE_PP_ -> y[17]$_DFF_P_ (15 levels, 6.17 ns of cell delay); adding a register stage at the cut that splits it. Lint clean. |
| 8 | verification | synthesis | synthesize | PASS: 6000 cycles, 4812 results bit-exact vs the golden model (latency 2, corner operands, mid-traffic resets) |
| 9 | synthesis | pd | implement | netlist: 1064 cells, 13817 um2, 149 flops, no latches (ABC delay-oriented) |
| 10 | pd | timing | analyze | placed (floorplan + placement): util 50 %, density 0.65; estimated setup WNS -0.18 ns |
| 11 | timing | pd | route | WNS -0.181 ns at 4.0 ns; worst path br[3][2]$_DFFE_PP_ -> pq[3][15]$_DFF_P_: 11 levels, cell 4.10 ns / net 0.00 ns (100% cell). Under 5 % of the period: route it and see. |
| 12 | pd | timing | analyze | routed: 0 DRC, 0 antenna nets, core 27026 um2, cell area 17233 um2 |
| 13 | timing | pd | relax_placement | WNS -0.053 ns at 4.0 ns; worst path br[0][5]$_DFFE_PP_ -> pq[0][15]$_DFF_P_: 12 levels, cell 3.94 ns / net 0.00 ns (100% cell). Logic-dominated but under 5 % of the period: one PD attempt first (cheaper than RTL). |
| 14 | pd | timing | analyze | placed (small or placement-related violation: lower utilisation and density, let repair_timing work): util 40 %, density 0.55; estimated setup WNS -0.22 ns |
| 15 | timing | rtl | pipeline | WNS -0.225 ns at 4.0 ns; worst path ar[1][3]$_DFFE_PP_ -> pq[1][14]$_DFF_P_: 12 levels, cell 4.11 ns / net 0.00 ns (100% cell). Logic-dominated; PD's attempt did not close it: needs a register stage. |
| 16 | rtl | verification | verify | latency 3, pipeline registers after: products, mult_mid; timing reports a logic-dominated path ar[1][3]$_DFFE_PP_ -> pq[1][14]$_DFF_P_ (12 levels, 4.11 ns of cell delay); adding a register stage at the cut that splits it. Lint clean. |
| 17 | verification | synthesis | synthesize | PASS: 6000 cycles, 4808 results bit-exact vs the golden model (latency 3, corner operands, mid-traffic resets) |
| 18 | synthesis | pd | implement | netlist: 1518 cells, 17563 um2, 250 flops, no latches (ABC delay-oriented) |
| 19 | pd | timing | analyze | placed (floorplan + placement): util 50 %, density 0.65; estimated setup WNS +0.14 ns |
| 20 | timing | pd | route | WNS +0.141 ns at 4.0 ns; worst path br[0][5]$_DFFE_PP_ -> phi[0][11]$_DFF_P_: 11 levels, cell 3.73 ns / net 0.00 ns (100% cell). Estimated closure; route it. |
| 21 | pd | timing | analyze | routed: 0 DRC, 0 antenna nets, core 34543 um2, cell area 19591 um2 |
| 22 | timing | orchestrator | closed | WNS +0.126 ns at 4.0 ns; worst path br[1][5]$_DFFE_PP_ -> phi[1][11]$_DFF_P_: 11 levels, cell 3.74 ns / net 0.00 ns (100% cell); hold WNS +0.062 ns. Setup and hold closed after detailed routing. |
| 23 | orchestrator | pd | area_recovery | closed; try to recover area before tape-out |
| 24 | pd | timing | analyze | placed (timing closed: try a denser floorplan to recover area): util 60 %, density 0.65; estimated setup WNS +0.07 ns |
| 25 | timing | pd | route | WNS +0.070 ns at 4.0 ns; worst path br[0][6]$_DFFE_PP_ -> phi[0][11]$_DFF_P_: 11 levels, cell 3.78 ns / net 0.00 ns (100% cell). Estimated closure; route it. |
| 26 | pd | timing | analyze | routed: 0 DRC, 0 antenna nets, core 28780 um2, cell area 19566 um2 |
| 27 | timing | orchestrator | closed | WNS +0.041 ns at 4.0 ns; worst path br[3][6]$_DFFE_PP_ -> phi[3][11]$_DFF_P_: 11 levels, cell 3.85 ns / net 0.00 ns (100% cell); hold WNS +0.067 ns. Setup and hold closed after detailed routing. |
