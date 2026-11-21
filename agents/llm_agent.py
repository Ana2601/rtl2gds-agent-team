"""`--policy claude`: each team member is a Claude tool-use loop.

The agent gets its role, the team protocol, its own SKILL.md, the incoming
message and a summary of the shared state. It acts through its role's tools
(the same functions the expert policies call) and ends its turn by sending
exactly one message to a teammate. The orchestrator and its sign-off criteria
stay deterministic.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import orfs
from .team import TOP, Board, Ctx, Msg, Synthesis
from .verify import lint, verify

MODEL = "claude-opus-5-5"
ROOT = Path(__file__).resolve().parent.parent

ROLES = {
    "rtl": ("RTL design engineer: write and revise the SystemVerilog for the spec", "rtl-design"),
    "verification": ("Verification engineer: sign off every RTL drop against the spec", "verification"),
    "synthesis": ("Synthesis engineer: Yosys/ABC on sky130hd via OpenROAD-flow-scripts", "synthesis"),
    "pd": ("Physical-design engineer: floorplan, place, CTS and route with OpenROAD", "physical-design"),
    "timing": ("Timing engineer: read OpenSTA results, diagnose, route fixes", "timing-analysis"),
}
KINDS = ("rtl: implement|pipeline|fix; verification: verify; synthesis: synthesize; "
         "pd: implement|route|relax_placement|area_recovery; timing: analyze; "
         "orchestrator: closed|infeasible|error|recovery_failed")


def _tool(name, desc, props, req):
    return {"name": name, "description": desc, "strict": True,
            "input_schema": {"type": "object", "properties": props, "required": req, "additionalProperties": False}}


SEND = _tool("send_message", "Hand off to a teammate. Ends your turn.",
             {"to": {"type": "string", "enum": ["rtl", "verification", "synthesis", "pd", "timing", "orchestrator"]},
              "kind": {"type": "string"}, "text": {"type": "string"}}, ["to", "kind", "text"])
TOOLS = {
    "rtl": [_tool("write_rtl", "Save the complete dot4 module and lint it (verilator -Wall).",
                  {"code": {"type": "string"}, "latency": {"type": "integer"}}, ["code", "latency"])],
    "verification": [_tool("run_verification", "Run the golden-model testbench on the current RTL.",
                           {"latency": {"type": "integer"}}, ["latency"])],
    "synthesis": [_tool("run_synthesis", "Synthesise the current RTL (new ORFS run).",
                        {"abc_area": {"type": "integer", "enum": [0, 1]}}, ["abc_area"])],
    "pd": [_tool("run_place", "Floorplan + place the current netlist with these knobs (new ORFS run).",
                 {"util": {"type": "integer"}, "density": {"type": "number"}}, ["util", "density"]),
           _tool("run_route", "CTS, global + detailed route and finish the current run.", {}, [])],
    "timing": [_tool("read_timing", "Setup/hold WNS and the parsed critical path after a stage.",
                     {"stage": {"type": "string", "enum": ["place", "finish"]}}, ["stage"])],
}


class ClaudeMember:
    def __init__(self, name: str):
        import anthropic
        self.name = name
        self.client = anthropic.Anthropic()
        role, skill = ROLES[name]
        self.system = (f"You are the {role} on a five-agent RTL-to-GDS team (RTL, verification, synthesis, "
                       f"physical design, timing) taking a block from spec to a sign-off GDS on sky130hd.\n"
                       f"Message kinds: {KINDS}.\nUse your tools, then send exactly one message.\n\n"
                       f"<spec>\n{(ROOT / 'spec' / 'dot4.md').read_text()}\n</spec>\n\n"
                       f"<skill>\n{(ROOT / 'skills' / skill / 'SKILL.md').read_text()}\n</skill>")

    def handle(self, m: Msg, c: Ctx, b: Board) -> None:
        state = {"latency": c.arch.latency if c.arch else None, "verified": bool(c.verified),
                 "flows_used": c.flows, "flow_budget": c.max_flows, "knobs": c.knobs.__dict__,
                 "last_run": {k: v for k, v in (c.runs[-1] if c.runs else {}).items() if k != "critical_path"}}
        messages = [{"role": "user", "content": f"Message from {m.sender} ({m.kind}): {m.text}\n"
                                                f"Data: {json.dumps(m.data, default=str)}\n"
                                                f"Team state: {json.dumps(state, default=str)}"}]
        tools = TOOLS[self.name] + [SEND]
        for _ in range(12):
            r = self.client.beta.messages.create(
                model=MODEL, max_tokens=16000, system=self.system, tools=tools, messages=messages,
                output_config={"effort": "high"}, betas=["server-side-fallback-2026-07-01"], fallbacks="default")
            if r.stop_reason == "refusal":
                raise RuntimeError(f"{self.name}: model declined: {r.stop_details}")
            messages.append({"role": "assistant", "content": r.content})
            calls = [x for x in r.content if x.type == "tool_use"]
            if not calls:
                break
            results = []
            for call in calls:
                if call.name == "send_message":
                    b.post(self.name, call.input["to"], call.input["kind"], call.input["text"])
                    return
                out = self._act(call.name, call.input, c)
                results.append({"type": "tool_result", "tool_use_id": call.id, "content": json.dumps(out, default=str)})
            messages.append({"role": "user", "content": results})
        b.post(self.name, "orchestrator", "error", "agent ended its turn without handing off")

    def _act(self, name: str, a: dict, c: Ctx) -> dict:
        if name == "write_rtl":
            f = c.out / "rtl" / f"L{a['latency']}" / f"{TOP}.sv"
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(a["code"])
            c.rtl = a["code"]
            from .rtl_gen import Arch
            c.arch = Arch(a["latency"], tuple(["custom"] * (a["latency"] - 1)))
            return {"file": str(f), "lint": lint(f, TOP)}
        if name == "run_verification":
            r = verify(c.out / "rtl" / f"L{a['latency']}" / f"{TOP}.sv", a["latency"], c.out / "verif" / f"L{a['latency']}", TOP)
            c.verified = {"latency": a["latency"], **r} if r["pass"] else None
            return r
        if name == "run_synthesis":
            c.knobs = orfs.Knobs(c.knobs.util, c.knobs.density, a["abc_area"])
            work = Synthesis._new_run(c)
            ok, _ = orfs.make(work, "synth")
            return {"ok": ok, **{k: v for k, v in orfs.metrics(work, TOP).items() if k.startswith("synth__design__instance")}}
        if name == "run_place":
            c.knobs = orfs.Knobs(a["util"], a["density"], c.knobs.abc_area)
            work = Synthesis._new_run(c)
            ok = orfs.make(work, "synth")[0] and orfs.make(work, "place")[0]
            met = orfs.metrics(work, TOP)
            return {"ok": ok, "setup_ws": met.get("detailedplace__timing__setup__ws"),
                    "utilization": met.get("detailedplace__design__instance__utilization")}
        if name == "run_route":
            ok, _ = orfs.make(c.current, "finish")
            met = orfs.metrics(c.current, TOP)
            c.runs[-1].update(drc=met.get("detailedroute__route__drc_errors"), setup_ws=met.get("finish__timing__setup__ws"),
                              hold_ws=met.get("finish__timing__hold__ws"), core_area=met.get("finish__design__core__area"),
                              cell_area=met.get("finish__design__instance__area"))
            return {"ok": ok, **{k: c.runs[-1].get(k) for k in ("drc", "setup_ws", "hold_ws", "core_area", "cell_area")}}
        if name == "read_timing":
            met = orfs.metrics(c.current, TOP)
            p = orfs.critical_path(c.current, TOP, a["stage"])
            key = "detailedplace" if a["stage"] == "place" else "finish"
            return {"setup_ws": met.get(f"{key}__timing__setup__ws"), "hold_ws": met.get("finish__timing__hold__ws"),
                    "period": c.period, "critical_path": p.as_dict() if p else None}
        return {"error": f"unknown tool {name}"}


def claude_team() -> dict:
    return {n: ClaudeMember(n) for n in ROLES}
