"""Fast tests (no OpenROAD needed): python -m unittest -v tests/test_team.py"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agents import orfs                                   # noqa: E402
from agents.rtl_gen import Arch, deeper, render          # noqa: E402
from agents.team import Board, Ctx, Msg, Timing          # noqa: E402
from agents.verify import golden, lint, verify           # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "L1"        # real ORFS reports of the L=1 design at 4 ns


class RtlAndVerification(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_every_pipeline_depth_is_lint_clean_and_bit_exact(self):
        a = Arch()
        seen = []
        while a:
            f = self.tmp / f"L{a.latency}" / "dot4.sv"
            f.parent.mkdir()
            f.write_text(render(a))
            self.assertTrue(lint(f)["pass"], a)
            r = verify(f, a.latency, self.tmp / f"v{a.latency}", n=2500)
            self.assertTrue(r["pass"], (a, r))
            self.assertGreater(r["results_checked"], 1800)
            seen.append(a.latency)
            a = deeper(a)
        self.assertEqual(seen, [1, 2, 3, 4])

    def test_verification_rejects_a_wrong_latency_claim(self):
        f = self.tmp / "dot4.sv"
        f.write_text(render(Arch(2, ("products",))))
        self.assertFalse(verify(f, 1, self.tmp / "neg", n=1000)["pass"])

    def test_golden_model_corner(self):
        cyc = [{"rst_n": 1, "in_valid": 1, "a": 0x80808080, "b": 0x80808080}] + \
              [{"rst_n": 1, "in_valid": 0, "a": 0, "b": 0}] * 4
        self.assertEqual(golden(cyc, 1)[2], {"valid": 1, "y": 65536})   # 4 x (-128 x -128)


class TimingParsing(unittest.TestCase):
    def test_critical_path_of_the_unpipelined_design(self):
        p = orfs.critical_path(FIX, "dot4", "finish")
        self.assertLess(p.slack, -1.5)
        self.assertGreater(p.levels, 12)
        self.assertTrue(p.endpoint.startswith("y["), p.endpoint)
        self.assertGreater(p.cell_delay, 0.7 * (p.cell_delay + p.net_delay))

    def test_timing_agent_sends_a_logic_dominated_miss_to_rtl_without_routing(self):
        c = Ctx(spec="", period=4.0, out=Path(tempfile.mkdtemp()))
        c.arch, c.current = Arch(1, ()), FIX
        c.runs = [{"run": 1, "latency": 1}]
        b = Board(log=lambda *_: None)
        Timing().handle(Msg(1, "pd", "timing", "analyze", "", {"stage": "place"}), c, b)
        m = b.messages[-1]
        self.assertEqual((m.to, m.kind), ("rtl", "pipeline"))
        self.assertIn("not worth routing", m.text)


class ClaudeRequestShape(unittest.TestCase):
    def test_member_hands_off_through_send_message(self):
        from agents import llm_agent
        seen = {}

        def create(**kw):
            seen.update(kw)
            return SimpleNamespace(stop_reason="tool_use", stop_details=None, content=[SimpleNamespace(
                type="tool_use", id="t1", name="send_message",
                input={"to": "verification", "kind": "verify", "text": "L=1 ready"})])

        mem = llm_agent.ClaudeMember.__new__(llm_agent.ClaudeMember)
        mem.name, mem.system = "rtl", "s"
        mem.client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
        c = Ctx(spec="", period=4.0, out=Path(tempfile.mkdtemp()))
        b = Board(log=lambda *_: None)
        mem.handle(Msg(1, "orchestrator", "rtl", "implement", "go"), c, b)
        self.assertEqual(seen["model"], "claude-opus-5-5")
        self.assertEqual(seen["fallbacks"], "default")
        self.assertEqual((b.messages[-1].to, b.messages[-1].kind), ("verification", "verify"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
