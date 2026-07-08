# corral — developer tasks
# Bash CLI; no build step. Targets wrap install, linking, and checks.

SHELL      := bash
BIN_DIR    ?= $(HOME)/.local/bin
CLI_DIR    := packages/cli
LAUNCHER   := $(CLI_DIR)/bin/corral
SOURCES    := $(LAUNCHER) $(wildcard $(CLI_DIR)/lib/*.sh)

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

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

.PHONY: lint
lint: ## Run shellcheck (follows sources from the entry point; no-op if absent)
	@if command -v shellcheck >/dev/null; then \
	  shellcheck -x --source-path=SCRIPTDIR -s bash $(LAUNCHER) install.sh $(CLI_DIR)/test/smoke.sh && echo "shellcheck: clean"; \
	else echo "shellcheck not installed — skipping (brew install shellcheck)"; fi

.PHONY: test
test: ## Run the smoke tests (no herdr server required)
	@bash $(CLI_DIR)/test/smoke.sh

.PHONY: check
check: lint test ## Lint + test
