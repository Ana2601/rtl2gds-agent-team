"""python -m agents [--policy expert|claude] [--max-flows 8] [--out results]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .report import write_report
from .team import Board, Ctx, Orchestrator, expert_team

ROOT = Path(__file__).resolve().parent.parent


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="RTL-to-GDS agent team (sky130hd, OpenROAD)")
    ap.add_argument("--policy", choices=["expert", "claude"], default="expert")
    ap.add_argument("--max-flows", type=int, default=8)
    ap.add_argument("--period", type=float, default=4.0)
    ap.add_argument("--out", type=Path, default=ROOT / "results")
    a = ap.parse_args(argv)
    if a.policy == "claude":
        from .llm_agent import claude_team
        team = claude_team()
    else:
        team = expert_team()
    ctx = Ctx(spec=(ROOT / "spec" / "dot4.md").read_text(), period=a.period, out=a.out, max_flows=a.max_flows)
    print(f"RTL-to-GDS team ({a.policy} policies), clock {a.period} ns, sky130hd")
    rep = Orchestrator(team, ctx, Board()).run()
    write_report(rep, a.out)
    print((a.out / "summary.md").read_text())
    return 0 if rep["signoff"] else 1


if __name__ == "__main__":
    sys.exit(main())
