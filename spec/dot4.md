# dot4: 4-lane signed dot-product unit (chip-level spec)

Computes `y = a0*b0 + a1*b1 + a2*b2 + a3*b3` on signed 8-bit operands, one result per clock.

## Interface

| Port | Dir | Width | Meaning |
|---|---|---|---|
| `clk` | in | 1 | clock |
| `rst_n` | in | 1 | asynchronous active-low reset |
| `in_valid` | in | 1 | operands valid this cycle |
| `a` | in | 32 | four signed 8-bit lanes, lane k = `a[8k +: 8]` |
| `b` | in | 32 | four signed 8-bit lanes |
| `out_valid` | out | 1 | `y` holds the result of an earlier `in_valid` cycle |
| `y` | out | 18 | signed dot product (exact; range -65024 ... 65536 fits in 18 bits) |

## Behaviour

- Full throughput: a new operand set may arrive every cycle.
- Inputs and output are registered. **The pipeline depth L between the input
  registers and the output register is the implementer's choice, 1 ≤ L ≤ 4**, fixed
  for the design. Operands presented with `in_valid` in cycle t produce `y` in cycle
  t + 1 + L with `out_valid = 1`; `out_valid` is 0 in every other cycle. `y` is
  don't-care while `out_valid = 0`.
- After reset, `out_valid = 0` until the first result.

## Implementation targets (sign-off criteria)

| Item | Target |
|---|---|
| Technology | SkyWater sky130, `sky130_fd_sc_hd`, typical corner (OpenROAD-flow-scripts platform `sky130hd`) |
| Clock | **4.0 ns (250 MHz)**. Not negotiable |
| Setup / hold | WNS ≥ 0 and hold WNS ≥ 0 after detailed routing |
| Physical | 0 DRC violations after detailed routing, 0 antenna violations |
| Area | as small as the clock target allows; minimum latency preferred over area |
| Verification | bit-exact against the reference model, including corner operands (-128, 127, 0) and reset in the middle of traffic |
