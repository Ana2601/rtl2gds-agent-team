PY ?= python3

.PHONY: test flow live check clean

## fast tests: RTL generator + verification at every depth, STA report parsing, agent decisions (~5 s)
test:
	$(PY) -m unittest -v tests/test_team.py

## the whole team, expert policies: spec -> RTL -> verified -> synthesised -> placed, routed -> GDS
## (runs OpenROAD-flow-scripts natively inside the openroad/orfs container, else through Docker)
flow:
	$(PY) -m agents --policy expert --max-flows 8

## the same team with every agent driven by Claude (needs ANTHROPIC_API_KEY)
live:
	$(PY) -m agents --policy claude --max-flows 8 --out results_live

check:
	$(PY) scripts/check_results.py

clean:
	rm -rf results/runs results/verif results_live tests/__pycache__ agents/__pycache__
