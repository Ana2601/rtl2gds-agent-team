"""Verification agent's tools: a Python golden model, vector generation, and an
Icarus Verilog testbench that replays the vectors and checks every cycle."""
from __future__ import annotations

import random
import re
from pathlib import Path

from .run import run


def golden(cycles: list[dict], latency: int) -> list[dict]:
    """Cycle model straight from the spec: result of cycle t appears at t+1+L."""
    out = [{"valid": 0, "y": None} for _ in cycles]
    for t, c in enumerate(cycles):
        if not c["rst_n"] or not c["in_valid"]:
            continue
        u = t + 1 + latency
        # a reset anywhere in (t, u] flushes the result
        if u < len(cycles) and all(cycles[k]["rst_n"] for k in range(t + 1, u + 1)):
            y = sum(_s8(c["a"] >> 8 * k) * _s8(c["b"] >> 8 * k) for k in range(4))
            out[u] = {"valid": 1, "y": y}
    return out


def _s8(x: int) -> int:
    x &= 0xFF
    return x - 256 if x & 0x80 else x


def vectors(n: int = 6000, seed: int = 1) -> list[dict]:
    rnd = random.Random(seed)
    corner = [0x80, 0x7F, 0x00, 0xFF, 0x01]
    cyc = []
    for t in range(n):
        def lane():
            return rnd.choice(corner) if rnd.random() < 0.3 else rnd.randrange(256)
        a = sum(lane() << 8 * k for k in range(4))
        b = sum(lane() << 8 * k for k in range(4))
        if t % 1000 == 3:                       # all-extreme operand sets
            a, b = (0x80808080, 0x80808080) if t % 2 else (0x7F7F7F7F, 0x80808080)
        rst = 0 if t < 3 or (t % 1500) in (700, 701) else 1     # reset mid-traffic
        cyc.append({"rst_n": rst, "in_valid": int(rnd.random() < 0.8), "a": a, "b": b})
    return cyc


TB = """`timescale 1ns/1ps
module tb;
    localparam int N = {n};
    logic clk = 0, rst_n, in_valid;
    logic [31:0] a, b;
    logic out_valid;
    logic signed [17:0] y;
    logic [65:0] stim [N];        // rst_n, in_valid, a, b
    logic [18:0] expv [N];        // valid, y
    logic        expk [N];        // 1 = compare y this cycle
    int errors = 0, checks = 0, results = 0;

    {top} dut (.*);
    always #5 clk = ~clk;

    initial begin
        $readmemh("stim.hex", stim);
        $readmemh("exp.hex", expv);
        $readmemh("chk.hex", expk);
        for (int t = 0; t < N; t++) begin
            {{rst_n, in_valid, a, b}} = stim[t];
            #1;
            checks++;
            if (out_valid !== expv[t][18] || (expk[t] && y !== $signed(expv[t][17:0]))) begin
                errors++;
                if (errors <= 10) $display("MISMATCH cycle %0d: out_valid=%b exp=%b y=%0d exp=%0d",
                                           t, out_valid, expv[t][18], y, $signed(expv[t][17:0]));
            end
            if (expk[t]) results++;
            @(posedge clk);
            #1;
        end
        $display("CHECKS %0d RESULTS %0d ERRORS %0d", checks, results, errors);
        if (errors == 0) $display("PASS"); else $display("FAIL");
        $finish;
    end
endmodule
"""


def verify(rtl: Path, latency: int, work: Path, top: str = "dot4", n: int = 6000) -> dict:
    work.mkdir(parents=True, exist_ok=True)
    cyc = vectors(n)
    exp = golden(cyc, latency)
    (work / "stim.hex").write_text("".join(
        f"{(c['rst_n'] << 65) | (c['in_valid'] << 64) | (c['a'] << 32) | c['b']:017x}\n" for c in cyc))
    (work / "exp.hex").write_text("".join(f"{(e['valid'] << 18) | ((e['y'] or 0) & 0x3FFFF):05x}\n" for e in exp))
    (work / "chk.hex").write_text("".join(f"{1 if e['valid'] else 0}\n" for e in exp))
    (work / "tb.sv").write_text(TB.format(n=n, top=top))
    rc, log = run(["iverilog", "-g2012", "-o", "sim.vvp", "tb.sv", str(rtl)], work, 120)
    if rc:
        return {"pass": False, "stage": "compile", "log": log[-2000:]}
    rc, log = run(["vvp", "-n", "sim.vvp"], work, 600)
    m = re.search(r"CHECKS (\d+) RESULTS (\d+) ERRORS (\d+)", log)
    ok = bool(m) and m.group(3) == "0" and "PASS" in log
    return {"pass": ok, "stage": "sim", "cycles": int(m.group(1)) if m else 0,
            "results_checked": int(m.group(2)) if m else 0,
            "errors": int(m.group(3)) if m else None,
            "mismatches": re.findall(r"MISMATCH.*", log)[:10]}


def lint(rtl: Path, top: str = "dot4") -> dict:
    rc, log = run(["verilator", "--lint-only", "-Wall", "--top-module", top, str(rtl)], rtl.parent, 120)
    msgs = [l for l in log.splitlines() if l.startswith("%")]
    return {"pass": rc == 0 and not msgs, "messages": msgs[:15]}
