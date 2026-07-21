# Local / agent shortcuts. Absolute root on this machine:
#   /Users/dex/.grok/plugins/ai-film-grok

ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
SKILL := $(ROOT)/skills/ai-film-grok
AIFILM := $(SKILL)/scripts/aifilm

.PHONY: help validate doctor test test-fast update inspect version

help:
	@echo "ROOT=$(ROOT)"
	@echo "targets: validate doctor test test-fast update inspect"

validate:
	grok plugin validate "$(ROOT)"

doctor:
	"$(AIFILM)" doctor

test:
	cd "$(SKILL)" && python3 -m pytest tests/ -q --tb=line

test-fast:
	cd "$(SKILL)" && python3 -m pytest tests/test_dispatch.py tests/test_craft_spine.py tests/test_delivery_gates.py -q --tb=line

update:
	grok plugin update ai-film-grok

inspect:
	grok plugin details ai-film-grok
	@echo "---"
	@ls -la "$(ROOT)/plugin.json"
	@test -L "$$HOME/.grok/skills/ai-film-grok" && readlink "$$HOME/.grok/skills/ai-film-grok" || true

version:
	@python3 -c "import json;print(json.load(open('$(ROOT)/plugin.json'))['version'])"
