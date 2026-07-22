# Local / agent shortcuts. Absolute root on this machine:
#   /Users/dex/.grok/plugins/ai-film-grok

ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
SKILL := $(ROOT)/skills/ai-film-grok
AIFILM := $(SKILL)/scripts/aifilm
RUNTIME_PYTHON := $(SKILL)/scripts/runtime-python

.PHONY: help validate doctor test test-fast release-check update inspect version sync-docs sync install-hooks

help:
	@echo "ROOT=$(ROOT)"
	@echo "targets: validate doctor test test-fast release-check sync-docs sync install-hooks update inspect"

validate:
	grok plugin validate "$(ROOT)"

doctor:
	"$(AIFILM)" doctor

test:
	cd "$(SKILL)" && "$$($(RUNTIME_PYTHON))" -m pytest tests/ -q --tb=line

test-fast:
	cd "$(SKILL)" && "$$($(RUNTIME_PYTHON))" -m pytest tests/test_dispatch.py tests/test_craft_spine.py tests/test_delivery_gates.py -q --tb=line

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
