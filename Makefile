# corral — developer tasks
# Python CLI (stdlib only; no build step). Targets wrap install, linking,
# artifact generation, and checks.

SHELL      := bash
PY         ?= python3
BIN_DIR    ?= $(HOME)/.local/bin
CLI_DIR    := packages/cli
OMZ_DIR    := packages/omz-plugin
LAUNCHER   := $(CLI_DIR)/bin/corral
ZSH_FILES  := $(OMZ_DIR)/corral.plugin.zsh $(OMZ_DIR)/_corral $(OMZ_DIR)/test/completions.zsh

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

.PHONY: install
install: ## Install corral (symlink into $BIN_DIR) via install.sh
	@./install.sh

.PHONY: link
link: ## Dev symlink: link the working tree's launcher into $BIN_DIR
	@mkdir -p "$(BIN_DIR)"
	@ln -sf "$(CURDIR)/$(LAUNCHER)" "$(BIN_DIR)/corral"
	@chmod +x "$(CURDIR)/$(LAUNCHER)"
	@echo "linked $(BIN_DIR)/corral -> $(CURDIR)/$(LAUNCHER)"

.PHONY: uninstall
uninstall: ## Remove the corral symlink from $BIN_DIR
	@rm -f "$(BIN_DIR)/corral" && echo "removed $(BIN_DIR)/corral"

.PHONY: generate
generate: ## Regenerate docs, config example, and the omz plugin from the registries
	@cd $(CLI_DIR) && PYTHONPATH=src $(PY) -m corral.generate

.PHONY: check-generated
check-generated: ## Verify the checked-in generated artifacts are fresh
	@cd $(CLI_DIR) && PYTHONPATH=src $(PY) -m corral.generate --check

.PHONY: lint
lint: ## Byte-compile the package, shellcheck install.sh, zsh -n the plugin
	@$(PY) -m compileall -q $(CLI_DIR)/src $(CLI_DIR)/tests && echo "compileall: clean"
	@if command -v shellcheck >/dev/null; then \
	  shellcheck -s bash install.sh && echo "shellcheck: clean"; \
	else echo "shellcheck not installed — skipping (brew install shellcheck)"; fi
	@if command -v zsh >/dev/null; then \
	  for f in $(ZSH_FILES); do zsh -n "$$f" || exit 1; done && echo "zsh -n: clean"; \
	else echo "zsh not installed — skipping zsh syntax checks"; fi

.PHONY: test
test: ## Run the Python test suite + zsh completion tests (no herdr server required)
	@cd $(CLI_DIR) && $(PY) -m unittest discover -s tests -t .
	@if command -v zsh >/dev/null; then \
	  zsh $(OMZ_DIR)/test/completions.zsh; \
	else echo "zsh not installed — skipping completion tests"; fi

.PHONY: check
check: lint check-generated test ## Lint + generated-artifact freshness + test
