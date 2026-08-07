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

.PHONY: help setup dev test test-fast test-hotpath check-all review clean validate doctor coverage audit audit-full lessons-audit release-check release-light update inspect version sync-docs sync install-hooks lock-runtime type smoke-console

help:
	@echo "ai-film-grok make targets"
	@echo "  check-all       secret-scan + validate + ruff + doctor + pytest not slow + hotpath + coverage 58%"
	@echo "  review          pre-PR: secret-scan + hotpath (fail-closed contracts)"
	@echo "  test-fast       same fast pytest as agents (not slow)"
	@echo "  test-hotpath    final/compose/gates fail-mode contracts only"
	@echo "  test            full pytest (includes slow)"
	@echo "  doctor          aifilm doctor"
	@echo "  release-light   docs + doctor core (CI is the real gate)"
	@echo "  release-check   package + full test suite"
	@echo "  lock-runtime    refresh runtime-lock.json fingerprints"
	@echo "  smoke-console   live localhost console regression (real aifilm serve + HTTP)"
	@echo "  sync-docs       regenerate README/GRAPH version pointers"
	@echo "  type            P5-1 mypy incremental typing gate (scoped)"
	@echo "  install-hooks   core.hooksPath=.githooks"

setup: install-hooks
	@echo "Setup completed."

dev:
	@echo "Development mode: watching changes..."

check-all:
	@bash "$(ROOT)/scripts/check-all.sh"

# Pre-PR / agent self-review: secrets + fail-closed hotpath only (fast).
review:
	@python3 "$(ROOT)/scripts/secret_scan.py"
	@$(MAKE) test-hotpath

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

# Live localhost console regression: starts the real `aifilm review-ui serve`
# on a loopback socket and drives the full flow end-to-end (gates, assets,
# hash-bound select 200/409, blocking gate 403, cross-origin 403, bad token 401,
# media-lib path-escape 404). Local one-click gate; mirrors the CI `console` job.
smoke-console:
	@"$(SKILL)/scripts/smoke_console.py"

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

# P5-1 incremental typing gate (mypy). Scoped to the already-clean modules;
# extend the file list as more modules are typed. Full-tree typing is iterative.
type:
	cd "$(SKILL)" && env -u PYTHONPATH "$$($(RUNTIME_PYTHON))" -m mypy \
		scripts/util/errors.py \
		scripts/util/validators.py \
		scripts/util/time.py \
		scripts/util/paths.py \
		scripts/util/logger.py \
		scripts/util/json_io.py \
		scripts/util/subprocess.py \
		scripts/util/retry.py \
		scripts/util/security_policy.py \
		scripts/util/config_loader.py \
		scripts/util/film_spec.py \
		scripts/util/structured_logger.py \
		scripts/core/constants.py \
		scripts/core/emit.py \
		scripts/core/paths.py \
		scripts/core/film_io.py \
		scripts/core/media_ops.py \
		scripts/core/skip_audit.py \
		scripts/core/attestation_audit.py \
		scripts/core/checkout_drift.py \
		scripts/core/gates.py

install-hooks:
	@git -C "$(ROOT)" config core.hooksPath .githooks
	@git -C "$(ROOT)" config core.fsmonitor false
	@chmod +x "$(ROOT)/.githooks/pre-push"
	@echo "Git hooks enabled via core.hooksPath=.githooks (fsmonitor=false)"
