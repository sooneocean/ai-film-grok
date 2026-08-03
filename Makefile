# Local / agent shortcuts. Absolute root on this machine:
#   /Users/dex/.grok/plugins/ai-film-grok

ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
SKILL := $(ROOT)/skills/ai-film-grok
AIFILM := $(SKILL)/scripts/aifilm
RUNTIME_PYTHON := $(SKILL)/scripts/runtime-python

.PHONY: help setup dev test test-fast check-all clean validate doctor coverage audit audit-full lessons-audit release-check update inspect version sync-docs sync install-hooks

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
	"$(AIFILM)" doctor

test:
	cd "$(SKILL)" && "$$($(RUNTIME_PYTHON))" -m pytest tests/ -q --tb=line
	"$$($(RUNTIME_PYTHON))" -m pytest skills/ai-film-project/tests tests/test_premium_pipeline_contracts.py -q --tb=line

test-fast:
	cd "$(SKILL)" && "$$($(RUNTIME_PYTHON))" -m pytest tests/test_dispatch.py tests/test_craft_spine.py tests/test_delivery_gates.py -q --tb=line

coverage:
	cd "$(SKILL)" && "$$($(RUNTIME_PYTHON))" -m coverage run --source=scripts -m pytest tests/ -q --tb=line -m "not slow"
	cd "$(SKILL)" && "$$($(RUNTIME_PYTHON))" -m coverage report --fail-under=58
	cd "$(SKILL)" && "$$($(RUNTIME_PYTHON))" -m coverage json -o coverage.json

audit:
	@"$$($(RUNTIME_PYTHON))" "$(ROOT)/scripts/project_audit.py" --run-tests --write-baseline

audit-full:
	@"$$($(RUNTIME_PYTHON))" "$(ROOT)/scripts/project_audit.py" --full-tests --write-baseline

lessons-audit:
	@"$$($(RUNTIME_PYTHON))" "$(ROOT)/scripts/audit_lessons.py" --write-report

release-check:
	@echo "[release] runtime=$$($(RUNTIME_PYTHON))"
	@echo "[release] CLI help"
	@"$(AIFILM)" --help >/dev/null
	@echo "[release] doctor"
	@"$(AIFILM)" doctor >/dev/null
	@echo "[release] package"
	@grok plugin validate "$(ROOT)"
	@$(MAKE) --no-print-directory test

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
	@chmod +x "$(ROOT)/.githooks/pre-push"
	@echo "Git hooks enabled via core.hooksPath=.githooks"
