"""results/summary.md: the sign-off table, every flow run, and the team's message log."""
from __future__ import annotations

from pathlib import Path


def _f(x, fmt="{:+.3f}"):
    return fmt.format(x) if isinstance(x, (int, float)) else "-"


def write_report(rep: dict, out: Path) -> None:
    L = []
    so = rep["signoff"]
    if so:
        L.append("## Sign-off\n")
        L.append("| Item | Result |\n|---|---|")
        L.append(f"| Architecture | {so['arch']} |")
        L.append(f"| Clock | {rep['period_ns']} ns ({1000 / rep['period_ns']:.0f} MHz), sky130hd typical |")
        L.append(f"| Setup WNS / TNS | {_f(so.get('setup_ws'))} ns / {_f(so.get('setup_tns'), '{:.3f}')} ns |")
        L.append(f"| Hold WNS | {_f(so.get('hold_ws'))} ns |")
        L.append(f"| DRC / antenna | {so.get('drc')} / {so.get('antenna')} |")
        L.append(f"| Core area / cell area | {_f(so.get('core_area'), '{:.0f}')} um² / {_f(so.get('cell_area'), '{:.0f}')} um² "
                 f"(utilisation {_f(so.get('utilization'), '{:.0%}')}) |")
        L.append(f"| Power (typical, default activity) | {so.get('power_mw')} mW |")
        v = rep.get("verification") or {}
        L.append(f"| Verification | {v.get('results_checked')} results over {v.get('cycles')} cycles, bit-exact |")
        L.append(f"| GDS | `signoff/dot4.gds` |")
    else:
        L.append("## No sign-off\n")
    L.append("\n## Flow runs\n")
    L.append("| Run | Latency | Util / density | Place WNS | Routed WNS | Hold WNS | DRC | Core area | Worst path (levels, cell / net delay) |")
    L.append("|---:|---:|---|---:|---:|---:|---:|---:|---|")
    for r in rep["runs"]:
        p = r.get("critical_path") or {}
        L.append(f"| {r['run']} | {r['latency']} | {r['util']} % / {r['density']} | {_f(r.get('place_ws'))} | "
                 f"{_f(r.get('setup_ws'))} | {_f(r.get('hold_ws'))} | {r.get('drc', '-') if r.get('drc') is not None else '-'} | "
                 f"{_f(r.get('core_area'), '{:.0f}')} | "
                 + (f"{p.get('startpoint')} → {p.get('endpoint')} ({p.get('levels')}, {p.get('cell_delay')} / {p.get('net_delay')} ns)"
                    if p else "-") + " |")
    L.append("\n## Team message log\n")
    L.append("| # | From | To | Kind | Message |\n|---:|---|---|---|---|")
    for m in rep["messages"]:
        L.append(f"| {m['n']} | {m['sender']} | {m['to']} | {m['kind']} | {m['text'].replace('|', chr(92) + '|')} |")
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.md").write_text("\n".join(L) + "\n")
