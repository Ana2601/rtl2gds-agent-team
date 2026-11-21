"""The RTL-to-GDS agent team: five agents and an orchestrator on a message board.

    Orchestrator ──implement──> RTL ──verify──> Verification ──synthesize──> Synthesis
         ^                       ^                                             │
         │                       │ timing: logic-dominated                     v implement
         │                       └─────────────────── Timing <──analyze── Physical design
         └──────── signoff-ready / infeasible ──────────┘        └──fix──>┘

Each agent owns its tools and follows its skills/<role>/SKILL.md. `expert`
policies implement the skill's rules deterministically (reproducible, used in
CI); `claude` policies (llm_agent.py) let Claude read the same skill and drive
the same tools. The orchestrator owns the sign-off criteria and the flow budget.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import orfs
from .rtl_gen import Arch, deeper, render
from .verify import lint, verify

TOP = "dot4"


@dataclass
class Msg:
    n: int
    sender: str
    to: str
    kind: str
    text: str
    data: dict = field(default_factory=dict)


@dataclass
class Board:
    log: callable = print
    messages: list = field(default_factory=list)

    def post(self, sender: str, to: str, kind: str, text: str, **data) -> Msg:
        m = Msg(len(self.messages) + 1, sender, to, kind, text, data)
        self.messages.append(m)
        self.log(f"  [{m.n:02d}] {sender:>12s} -> {to:<12s} {kind}: {text}")
        return m


@dataclass
class Ctx:
    spec: str
    period: float
    out: Path
    max_flows: int = 8
    flows: int = 0                          # PD runs started (each is one ORFS run)
    arch: Arch | None = None
    rtl: str = ""
    verified: dict | None = None
    knobs: orfs.Knobs = field(default_factory=orfs.Knobs)
    runs: list = field(default_factory=list)  # one record per ORFS run
    current: Path | None = None               # ORFS work dir of the current run
    signoff: dict | None = None


# --------------------------------------------------------------------------- #
# expert policies (the skills, as code)
# --------------------------------------------------------------------------- #
class RTL:
    name = "rtl"

    def handle(self, m: Msg, c: Ctx, b: Board) -> None:
        if m.kind == "implement":
            c.arch = Arch(1, ())                    # skill: start from the minimum latency
            why = "minimum latency the spec allows (L=1); pipeline only if timing proves it necessary"
        elif m.kind == "pipeline":
            nxt = deeper(c.arch, m.data.get("endpoint"))
            if nxt is None:
                b.post(self.name, "orchestrator", "infeasible",
                       f"no register stage left that splits the path ending at {m.data.get('endpoint')} "
                       f"within the latency budget (L<=4)", **m.data)
                return
            why = (f"timing reports a logic-dominated path {m.data.get('startpoint')} -> {m.data.get('endpoint')} "
                   f"({m.data.get('levels')} levels, {m.data.get('cell_delay')} ns of cell delay); "
                   f"adding a register stage at the cut that splits it")
            c.arch = nxt
        else:
            return
        c.rtl = render(c.arch, TOP)
        f = c.out / "rtl" / f"L{c.arch.latency}" / f"{TOP}.sv"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(c.rtl)
        li = lint(f, TOP)
        if not li["pass"]:
            b.post(self.name, "orchestrator", "error", "generated RTL does not lint", messages=li["messages"])
            return
        b.post(self.name, "verification", "verify", f"{c.arch.describe()}; {why}. Lint clean.",
               rtl=str(f), latency=c.arch.latency)


class Verification:
    name = "verification"

    def handle(self, m: Msg, c: Ctx, b: Board) -> None:
        if m.kind != "verify":
            return
        r = verify(Path(m.data["rtl"]), m.data["latency"], c.out / "verif" / f"L{m.data['latency']}", TOP)
        if r["pass"]:
            c.verified = {"rtl": m.data["rtl"], "latency": m.data["latency"], **r}
            b.post(self.name, "synthesis", "synthesize",
                   f"PASS: {r['cycles']} cycles, {r['results_checked']} results bit-exact vs the golden model "
                   f"(latency {m.data['latency']}, corner operands, mid-traffic resets)", rtl=m.data["rtl"])
        else:
            c.verified = None
            b.post(self.name, "rtl", "fix", f"FAIL at {r['stage']}: {(r.get('mismatches') or [''])[0]}", result=r)


class Synthesis:
    name = "synthesis"

    def handle(self, m: Msg, c: Ctx, b: Board) -> None:
        if m.kind != "synthesize":
            return
        c.knobs = orfs.Knobs(util=50, density=0.65, abc_area=0)     # skill: delay-oriented ABC when the clock is tight
        work = self._new_run(c)
        t = time.time()
        ok, log = orfs.make(work, "synth")
        met = orfs.metrics(work, TOP)
        cells = orfs.netlist_cells(work, TOP)
        latches = {k: v for k, v in cells.items() if "dlx" in k or "dlrt" in k}
        flops = sum(v for k, v in cells.items() if "df" in k)
        rec = c.runs[-1]
        rec.update(synth_area=met.get("synth__design__instance__area"), flops=flops, synth_s=round(time.time() - t))
        if not ok or latches:
            b.post(self.name, "rtl", "fix", "synthesis failed" if not ok else f"latches inferred: {latches}")
            return
        b.post(self.name, "pd", "implement",
               f"netlist: {met.get('synth__design__instance__count')} cells, "
               f"{met.get('synth__design__instance__area'):.0f} um2, {flops} flops, no latches (ABC delay-oriented)")

    @staticmethod
    def _new_run(c: Ctx) -> Path:
        c.flows += 1
        work = c.out / "runs" / f"run{c.flows:02d}_L{c.arch.latency}_u{c.knobs.util}_d{c.knobs.density}"
        orfs.prepare(work, c.rtl, TOP, c.period, c.knobs)
        c.current = work
        c.runs.append({"run": c.flows, "latency": c.arch.latency, "arch": c.arch.describe(),
                       "util": c.knobs.util, "density": c.knobs.density, "dir": str(work)})
        return work


class PD:
    name = "pd"

    def handle(self, m: Msg, c: Ctx, b: Board) -> None:
        if m.kind == "implement":
            self._place(c, b, "floorplan + placement")
        elif m.kind == "route":
            self._finish(c, b)
        elif m.kind in ("relax_placement", "area_recovery"):
            if c.flows >= c.max_flows:
                b.post(self.name, "orchestrator", "budget", "flow budget exhausted")
                return
            if m.kind == "relax_placement":
                c.knobs = orfs.Knobs(util=max(c.knobs.util - 10, 30), density=round(max(c.knobs.density - 0.1, 0.4), 2))
                why = "small or placement-related violation: lower utilisation and density, let repair_timing work"
            else:
                c.knobs = orfs.Knobs(util=c.knobs.util + 10, density=c.knobs.density)
                why = "timing closed: try a denser floorplan to recover area"
            Synthesis._new_run(c)
            ok, _ = orfs.make(c.current, "synth")
            self._place(c, b, why, area_recovery=(m.kind == "area_recovery"))

    def _place(self, c: Ctx, b: Board, why: str, area_recovery: bool = False) -> None:
        t = time.time()
        ok, log = orfs.make(c.current, "place")
        met = orfs.metrics(c.current, TOP)
        rec = c.runs[-1]
        rec.update(place_ws=met.get("detailedplace__timing__setup__ws"), place_s=round(time.time() - t),
                   area_recovery=area_recovery)
        if not ok:
            b.post(self.name, "orchestrator", "error", "placement failed")
            return
        b.post(self.name, "timing", "analyze", f"placed ({why}): util {c.knobs.util} %, density {c.knobs.density}; "
               f"estimated setup WNS {rec['place_ws']:+.2f} ns", stage="place")

    def _finish(self, c: Ctx, b: Board) -> None:
        t = time.time()
        ok, log = orfs.make(c.current, "finish")
        met = orfs.metrics(c.current, TOP)
        rec = c.runs[-1]
        drc = met.get("detailedroute__route__drc_errors")
        ant = met.get("detailedroute__antenna__violating__nets", 0)
        rec.update(route_s=round(time.time() - t), drc=drc, antenna=ant,
                   setup_ws=met.get("finish__timing__setup__ws"), setup_tns=met.get("finish__timing__setup__tns"),
                   hold_ws=met.get("finish__timing__hold__ws"), core_area=met.get("finish__design__core__area"),
                   cell_area=met.get("finish__design__instance__area"),
                   utilization=met.get("finish__design__instance__utilization"),
                   power_mw=round(met.get("finish__power__total", 0) * 1000, 3))
        if not ok:
            b.post(self.name, "orchestrator", "error", "routing/finish failed")
            return
        if drc:
            if rec.get("area_recovery"):
                b.post(self.name, "orchestrator", "recovery_failed", f"denser floorplan leaves {drc} DRC violations")
            else:
                b.post(self.name, "pd", "relax_placement", f"{drc} DRC violations after detailed routing")
            return
        b.post(self.name, "timing", "analyze",
               f"routed: 0 DRC, {ant} antenna nets, core {rec['core_area']:.0f} um2, cell area {rec['cell_area']:.0f} um2",
               stage="finish")


class Timing:
    name = "timing"

    def handle(self, m: Msg, c: Ctx, b: Board) -> None:
        if m.kind != "analyze":
            return
        stage = m.data["stage"]
        met = orfs.metrics(c.current, TOP)
        ws = met.get("detailedplace__timing__setup__ws" if stage == "place" else "finish__timing__setup__ws")
        hold = met.get("finish__timing__hold__ws", 0) if stage == "finish" else 0
        p = orfs.critical_path(c.current, TOP, stage)
        c.runs[-1]["critical_path"] = p.as_dict() if p else None
        share = p.cell_delay / max(p.cell_delay + p.net_delay, 1e-9) if p else 1.0
        logic = p is not None and share >= 0.7 and p.levels >= 6
        ev = dict(startpoint=p.startpoint, endpoint=p.endpoint, levels=p.levels,
                  cell_delay=p.cell_delay, net_delay=p.net_delay, wns=ws) if p else {"wns": ws}
        small = ws is not None and ws > -0.05 * c.period
        desc = (f"WNS {ws:+.3f} ns at {c.period} ns; worst path {p.startpoint} -> {p.endpoint}: {p.levels} levels, "
                f"cell {p.cell_delay:.2f} ns / net {p.net_delay:.2f} ns ({share:.0%} cell)") if p else f"WNS {ws}"
        tries = self._pd_tries(c)
        if ws is not None and ws >= 0 and hold >= 0:
            if stage == "place":
                b.post(self.name, "pd", "route", f"{desc}. Estimated closure; route it.")
            else:
                b.post(self.name, "orchestrator", "closed",
                       f"{desc}; hold WNS {hold:+.3f} ns. Setup and hold closed after detailed routing.", **ev)
            return
        if c.runs[-1].get("area_recovery"):
            b.post(self.name, "orchestrator", "recovery_failed", f"{desc}: the denser floorplan breaks timing", **ev)
        elif hold < 0:
            b.post(self.name, "pd", "relax_placement", f"hold WNS {hold:+.3f} ns: PD repair", **ev)
        elif stage == "place" and small:
            b.post(self.name, "pd", "route", f"{desc}. Under 5 % of the period: route it and see.", **ev)
        elif logic and small and tries < 1:
            b.post(self.name, "pd", "relax_placement",
                   f"{desc}. Logic-dominated but under 5 % of the period: one PD attempt first (cheaper than RTL).", **ev)
        elif logic:
            why = ("PD's attempt did not close it" if small or tries >= 1 else
                   f"{abs(ws) / c.period:.0%} of the period, not worth routing")
            b.post(self.name, "rtl", "pipeline", f"{desc}. Logic-dominated; {why}: needs a register stage.", **ev)
        elif tries < 2:
            b.post(self.name, "pd", "relax_placement", f"{desc}. Wire/placement-dominated.", **ev)
        else:
            b.post(self.name, "rtl", "pipeline", f"{desc}. PD has tried twice at this latency.", **ev)

    @staticmethod
    def _pd_tries(c: Ctx) -> int:
        """ORFS runs already made at the current latency beyond the first one."""
        return sum(1 for r in c.runs if r["latency"] == c.arch.latency) - 1


# --------------------------------------------------------------------------- #
class Orchestrator:
    name = "orchestrator"

    def __init__(self, agents: dict, ctx: Ctx, board: Board):
        self.agents, self.c, self.b = agents, ctx, board

    def run(self) -> dict:
        c, b = self.c, self.b
        b.post(self.name, "rtl", "implement", f"implement {TOP} per spec: clock {c.period} ns on sky130hd, "
               f"sign-off = verified, setup/hold WNS >= 0, 0 DRC")
        recovered = False
        steps = 0
        while steps < 200:
            steps += 1
            pending = [m for m in b.messages if not getattr(m, "_done", False)]
            if not pending:
                break
            m = pending[0]
            m._done = True
            if m.to != self.name:
                self.agents[m.to].handle(m, c, b)
                continue
            if m.kind == "closed":
                if not (c.verified and c.verified["latency"] == c.arch.latency):
                    b.post(self.name, "verification", "verify", "sign-off needs the final RTL verified",
                           rtl=str(c.out / "rtl" / f"L{c.arch.latency}" / f"{TOP}.sv"), latency=c.arch.latency)
                    continue
                c.signoff = dict(c.runs[-1])
                if not recovered and c.flows < c.max_flows:
                    recovered = True
                    b.post(self.name, "pd", "area_recovery", "closed; try to recover area before tape-out")
                    continue
                break
            if m.kind == "recovery_failed":
                b.post(self.name, "orchestrator", "signoff", "keeping the previous closed run")
                break
            if m.kind in ("infeasible", "error", "budget"):
                break
        return self.report()

    def report(self) -> dict:
        c = self.c
        so = c.signoff
        if so:
            so["artefacts"] = orfs.artefacts(Path(so["dir"]), TOP, c.out / "signoff")
            (c.out / "signoff" / f"{TOP}.sv").write_text(Path(c.out / "rtl" / f"L{so['latency']}" / f"{TOP}.sv").read_text())
        rep = {"design": TOP, "period_ns": c.period, "signoff": so, "flows": c.flows, "runs": c.runs,
               "verification": c.verified,
               "messages": [m.__dict__ | {"data": {k: v for k, v in m.data.items() if k != "result"}}
                            for m in self.b.messages]}
        for m in rep["messages"]:
            m.pop("_done", None)
        c.out.mkdir(parents=True, exist_ok=True)
        text = json.dumps(rep, indent=2, default=str)
        for root in {str(c.out.resolve()), str(c.out)}:      # keep machine paths out of the report
            text = text.replace(root, c.out.name)
        (c.out / "report.json").write_text(text + "\n")
        return json.loads(text)


def expert_team() -> dict:
    return {a.name: a for a in (RTL(), Verification(), Synthesis(), PD(), Timing())}
