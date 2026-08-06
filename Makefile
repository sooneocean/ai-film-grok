# Local / agent shortcuts.
#   Git root (edit + commit here):   /Users/dex/.grok/ai-film-grok
#   Runtime mirror (read by plugin): /Users/dex/.grok/plugins/ai-film-grok
#                                     -> refresh after push via `grok plugin update`
#   NOTE: the two checkouts share history but can fork — always commit in the
#   git root above, then `grok plugin update` to sync the runtime mirror.
#
# Optimization loop (default agent path):
#   make check-all          # secret-scan + validate + ruff + doctor + pytest not slow + hotpath + coverage 58%
#   make release-light      # docs + doctor core (light gate; CI is the real gate)
#   git push                # CI gates run on the server and are the final authority
# Full suite before a heavy release:
#   make release-check      # or AIFILM_RELEASE_GATE=full git push

ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
SKILL := $(ROOT)/skills/ai-film-grok
AIFILM := $(SKILL)/scripts/aifilm
RUNTIME_PYTHON := $(SKILL)/scripts/runtime-python

.PHONY: help setup dev test test-fast test-hotpath check-all clean validate doctor coverage audit audit-full lessons-audit release-check release-light update inspect version sync-docs sync install-hooks lock-runtime

help:
	@echo "ai-film-grok make targets"
	@echo "  check-all       secret-scan + validate + ruff + doctor + pytest not slow + hotpath + coverage 58%"
	@echo "  test-fast       same fast pytest as agents (not slow)"
	@echo "  test-hotpath    final/compose/gates fail-mode contracts only"
	@echo "  test            full pytest (includes slow)"
	@echo "  doctor          aifilm doctor"
	@echo "  release-light   docs + doctor core (CI is the real gate)"
	@echo "  release-check   package + full test suite"
	@echo "  lock-runtime    refresh runtime-lock.json fingerprints"
	@echo "  sync-docs       regenerate README/GRAPH version pointers"
	@echo "  install-hooks   core.hooksPath=.githooks"

setup: install-hooks
	@echo "Setup completed."

dev:
	@echo "Development mode: watching changes..."

check-all:
	@bash "$(ROOT)/scripts/check-all.sh"

clean:
	@rm -rf "$(SKILL)/.pytest_cache" "$(SKILL)/.ruff_cache" "$(SKILL)/coverage.json" "$(SKILL)/.coverage"
	@echo "Clean completed."

validate:
	grok plugin validate "$(ROOT)"

doctor:
	env -u PYTHONPATH "$(AIFILM)" doctor

test:
	cd "$(SKILL)" && env -u PYTHONPATH "$$($(RUNTIME_PYTHON))" -m pytest tests/ -q --tb=line
	env -u PYTHONPATH "$$($(RUNTIME_PYTHON))" -m pytest skills/ai-film-project/tests tests/test_premium_pipeline_contracts.py -q --tb=line

# Real agent fast path (exclude @pytest.mark.slow)
test-fast:
	cd "$(SKILL)" && env -u PYTHONPATH "$$($(RUNTIME_PYTHON))" -m pytest tests/ -q --tb=line -m "not slow"

test-hotpath:
	cd "$(SKILL)" && env -u PYTHONPATH "$$($(RUNTIME_PYTHON))" -m pytest tests/ -q --tb=line -m "hotpath and not slow"

coverage:
	cd "$(SKILL)" && env -u PYTHONPATH "$$($(RUNTIME_PYTHON))" -m coverage run --source=scripts -m pytest tests/ -q --tb=line -m "not slow"
	cd "$(SKILL)" && env -u PYTHONPATH "$$($(RUNTIME_PYTHON))" -m coverage report --fail-under=58
	cd "$(SKILL)" && env -u PYTHONPATH "$$($(RUNTIME_PYTHON))" -m coverage json -o coverage.json

audit:
	@"$$($(RUNTIME_PYTHON))" "$(ROOT)/scripts/project_audit.py" --run-tests --write-baseline

audit-full:
	@"$$($(RUNTIME_PYTHON))" "$(ROOT)/scripts/project_audit.py" --full-tests --write-baseline

lessons-audit:
	@"$$($(RUNTIME_PYTHON))" "$(ROOT)/scripts/audit_lessons.py" --write-report

# Full local release (heavy). Prefer release-light for day-to-day push.
release-check:
	@echo "[release] runtime=$$($(RUNTIME_PYTHON))"
	@AIFILM_RELEASE_GATE=full "$$($(RUNTIME_PYTHON))" "$(ROOT)/scripts/release_gate.py" --mode full

release-light:
	@"$$($(RUNTIME_PYTHON))" "$(ROOT)/scripts/release_gate.py" --mode light

lock-runtime:
	@"$(AIFILM)" lock-runtime

update:
	grok plugin update ai-film-grok

inspect:
	grok plugin details ai-film-grok
	@echo "---"
	@ls -la "$(ROOT)/plugin.json"
	@test -L "$$HOME/.grok/skills/ai-film-grok" && readlink "$$HOME/.grok/skills/ai-film-grok" || true

version:
	@"$$($(RUNTIME_PYTHON))" -c "import json;print(json.load(open('$(ROOT)/plugin.json'))['version'])"

sync-docs:
	@python3 "$(ROOT)/scripts/sync_project_docs.py"

sync:
	@python3 "$(ROOT)/scripts/sync_project_docs.py" --commit --push

install-hooks:
	@git -C "$(ROOT)" config core.hooksPath .githooks
	@git -C "$(ROOT)" config core.fsmonitor false
	@chmod +x "$(ROOT)/.githooks/pre-push"
	@echo "Git hooks enabled via core.hooksPath=.githooks (fsmonitor=false)"
