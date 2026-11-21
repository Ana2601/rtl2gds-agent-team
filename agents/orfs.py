"""OpenROAD-flow-scripts (ORFS) driver and report parsers.

Runs the real flow - Yosys/ABC synthesis, OpenROAD floorplan, placement, CTS,
global/detailed routing, finishing, OpenSTA - for sky130hd. Either natively
(inside the openroad/orfs container, as CI does) or through Docker.
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from .run import run

IMAGE = os.environ.get("ORFS_IMAGE", "openroad/orfs:latest")
ORFS = Path(os.environ.get("ORFS_ROOT", "/OpenROAD-flow-scripts"))
PLATFORM = "sky130hd"
NATIVE = (ORFS / "flow" / "Makefile").exists()

SDC = """current_design {top}
set clk_name  core_clock
set clk_port  [get_ports clk]
set period    {period}
create_clock -name $clk_name -period $period $clk_port
# I/O budget: 20 % of the period on each side (the block sits between registers)
set_input_delay  [expr $period * 0.2] -clock $clk_name [delete_from_list [all_inputs] $clk_port]
set_output_delay [expr $period * 0.2] -clock $clk_name [all_outputs]
"""

CONFIG = """export PLATFORM          = {platform}
export DESIGN_NAME       = {top}
export DESIGN_NICKNAME   = {top}
export VERILOG_FILES     = {root}/{rtl}
export SDC_FILE          = {root}/constraint.sdc
export CORE_UTILIZATION  = {util}
export CORE_ASPECT_RATIO = 1
export PLACE_DENSITY     = {density}
export ABC_AREA          = {abc_area}
"""

STAGE_TARGET = {"synth": "synth", "place": "place", "route": "route", "finish": "finish"}
STAGE_REPORT = {"place": "3_detailed_place.rpt", "cts": "4_cts_final.rpt",
                "route": "5_global_route.rpt", "finish": "6_finish.rpt"}


@dataclass
class Knobs:
    util: int = 50
    density: float = 0.65
    abc_area: int = 0


def prepare(work: Path, rtl_text: str, top: str, period: float, knobs: Knobs) -> None:
    work.mkdir(parents=True, exist_ok=True)
    (work / f"{top}.sv").write_text(rtl_text)
    (work / "constraint.sdc").write_text(SDC.format(top=top, period=period))
    root = str(work.resolve()) if NATIVE else "/work"
    (work / "config.mk").write_text(CONFIG.format(platform=PLATFORM, top=top, root=root, rtl=f"{top}.sv",
                                                  util=knobs.util, density=knobs.density,
                                                  abc_area=knobs.abc_area))


def make(work: Path, target: str, timeout: int = 3600) -> tuple[bool, str]:
    """Run ORFS up to `target` (incremental: earlier stages are reused)."""
    if NATIVE:
        cmd = ["make", "-C", str(ORFS / "flow"), f"DESIGN_CONFIG={work.resolve()}/config.mk",
               f"WORK_HOME={work.resolve()}", target]
    else:
        cmd = ["docker", "run", "--rm", "--platform", "linux/amd64", "-v", f"{work.resolve()}:/work",
               IMAGE, "bash", "-c",
               f"cd /OpenROAD-flow-scripts/flow && make DESIGN_CONFIG=/work/config.mk WORK_HOME=/work {target}"]
    rc, log = run(cmd, work, timeout)
    (work / f"make_{target}.log").write_text(log)
    return rc == 0, log


def _base(work: Path, top: str, kind: str) -> Path:
    return work / kind / PLATFORM / top / "base"


def metrics(work: Path, top: str) -> dict:
    """All per-step ORFS metrics merged (later steps override earlier ones)."""
    m: dict = {}
    for f in sorted(glob.glob(str(_base(work, top, "logs") / "*.json"))):
        try:
            m.update(json.loads(Path(f).read_text()))
        except json.JSONDecodeError:
            pass
    return m


def netlist_cells(work: Path, top: str) -> dict:
    v = _base(work, top, "results") / "1_synth.v"
    if not v.exists():
        v = next(iter(glob.glob(str(_base(work, top, "results") / "1_*.v"))), None)
        v = Path(v) if v else None
    if not v:
        return {}
    text = v.read_text()
    cells = re.findall(r"^\s*(sky130_fd_sc_hd__\w+)\s+\S+\s*\(", text, re.M)
    out: dict = {}
    for c in cells:
        out[c] = out.get(c, 0) + 1
    return out


@dataclass
class Path_:
    slack: float
    startpoint: str
    endpoint: str
    levels: int
    cell_delay: float
    net_delay: float
    arrival: float
    required: float
    cells: list

    def as_dict(self) -> dict:
        d = dict(self.__dict__)
        d["cells"] = self.cells[:40]
        return d


def critical_path(work: Path, top: str, stage: str) -> Path_ | None:
    """Parse the worst setup path (report_checks -path_delay max, with fanout/cap/slew fields)."""
    rpt = _base(work, top, "reports") / STAGE_REPORT[stage]
    if not rpt.exists():
        return None
    text = rpt.read_text()
    # every reported path, keep the worst max-delay (setup) one that has fanout fields
    best = None
    for m in re.finditer(r"(Startpoint: .*?)\n\s*(-?[\d.]+)\s+slack", text, re.S):
        blk, sl = m.group(1), float(m.group(2))
        if "Path Type: max" in blk and "Fanout" in blk and (best is None or sl < best[1]):
            best = (blk, sl)
    if not best:
        return None
    block, slack = best
    sp = re.search(r"Startpoint: (\S+)", block).group(1)
    ep = re.search(r"Endpoint: (\S+)", block).group(1)
    lines = block.splitlines()
    # data path: from the startpoint's clock pin to "data arrival time"
    start = next((i for i, l in enumerate(lines) if sp in l and re.search(r"/(CLK|CLK_N)\b", l)), None)
    if start is None:          # input-port startpoint
        start = next((i for i, l in enumerate(lines) if f" {sp} (in)" in l), 0)
    end = next(i for i, l in enumerate(lines) if "data arrival time" in l)
    cell, net, levels, cells = 0.0, 0.0, 0, []
    for l in lines[start + 1:end]:
        nums = re.findall(r"-?\d+\.\d+|\b\d+\b(?=\s)", l.split("^")[0].split(" v ")[0])
        pin = re.search(r"[\^v] (\S+) \((sky130_fd_sc_hd__\w+)\)", l)
        if not pin:
            continue
        vals = [float(x) for x in re.findall(r"-?\d+\.\d+", l)]
        is_output = len(re.findall(r"^\s*\d+\s", l)) == 1           # driver lines start with fanout
        if is_output and len(vals) >= 4:
            cell += vals[-2]
            levels += 1
            cells.append(pin.group(2).replace("sky130_fd_sc_hd__", ""))
        elif len(vals) >= 2:
            net += vals[-2]
    arr = float(re.search(r"(-?[\d.]+)\s+data arrival time", block).group(1))
    req = re.search(r"(-?[\d.]+)\s+data required time", block)
    return Path_(slack, sp, ep, max(levels - 1, 0), round(cell, 3), round(net, 3), arr,
                 float(req.group(1)) if req else 0.0, cells)


def artefacts(work: Path, top: str, dest: Path) -> dict:
    """Copy the GDS and the layout images ORFS renders into dest."""
    dest.mkdir(parents=True, exist_ok=True)
    out = {}
    gds = _base(work, top, "results") / "6_final.gds"
    if gds.exists():
        shutil.copy(gds, dest / f"{top}.gds")
        out["gds"] = str(dest / f"{top}.gds")
    for img in ("final_all", "final_placement", "final_routing", "final_clocks", "final_congestion"):
        f = _base(work, top, "reports") / f"{img}.webp"
        if f.exists():
            shutil.copy(f, dest / f.name)
            out[img] = str(dest / f.name)
    return out
