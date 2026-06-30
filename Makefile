SHELL := /bin/bash
PYTHON ?= .venv/bin/python
NPM ?= npm
NPX ?= npx
RUNTIME_DIR := .runtime
API_PID := $(RUNTIME_DIR)/api.pid
UI_PID := $(RUNTIME_DIR)/ui.pid
API_LOG := $(RUNTIME_DIR)/api.log
UI_LOG := $(RUNTIME_DIR)/ui.log
API_HOST ?= 0.0.0.0
UI_HOST ?= 0.0.0.0

.PHONY: start stop restart status logs migrate api ui

start: migrate
	@mkdir -p $(RUNTIME_DIR)
	@if [ -f $(API_PID) ] && kill -0 $$(cat $(API_PID)) 2>/dev/null; then \
		echo "API already running: $$(cat $(API_PID))"; \
	else \
		echo "Starting API..."; \
		nohup $(PYTHON) run.py > $(API_LOG) 2>&1 & echo $$! > $(API_PID); \
	fi
	@if [ -f $(UI_PID) ] && kill -0 $$(cat $(UI_PID)) 2>/dev/null; then \
		echo "UI already running: $$(cat $(UI_PID))"; \
	else \
		echo "Starting UI..."; \
		nohup $(NPX) vite --host $(UI_HOST) > $(UI_LOG) 2>&1 & echo $$! > $(UI_PID); \
	fi
	@$(MAKE) status

api: migrate
	@mkdir -p $(RUNTIME_DIR)
	@if [ -f $(API_PID) ] && kill -0 $$(cat $(API_PID)) 2>/dev/null; then \
		echo "API already running: $$(cat $(API_PID))"; \
	else \
		echo "Starting API..."; \
		nohup $(PYTHON) run.py > $(API_LOG) 2>&1 & echo $$! > $(API_PID); \
	fi

ui:
	@mkdir -p $(RUNTIME_DIR)
	@if [ -f $(UI_PID) ] && kill -0 $$(cat $(UI_PID)) 2>/dev/null; then \
		echo "UI already running: $$(cat $(UI_PID))"; \
	else \
		echo "Starting UI..."; \
		nohup $(NPX) vite --host $(UI_HOST) > $(UI_LOG) 2>&1 & echo $$! > $(UI_PID); \
	fi

stop:
	@if [ -f $(UI_PID) ]; then \
		pid=$$(cat $(UI_PID)); \
		if kill -0 $$pid 2>/dev/null; then echo "Stopping UI $$pid..."; kill $$pid; else echo "UI not running"; fi; \
		rm -f $(UI_PID); \
	else echo "UI not running"; fi
	@if [ -f $(API_PID) ]; then \
		pid=$$(cat $(API_PID)); \
		if kill -0 $$pid 2>/dev/null; then echo "Stopping API $$pid..."; kill $$pid; else echo "API not running"; fi; \
		rm -f $(API_PID); \
	else echo "API not running"; fi

restart: stop start

status:
	@if [ -f $(API_PID) ] && kill -0 $$(cat $(API_PID)) 2>/dev/null; then echo "API running: $$(cat $(API_PID))"; else echo "API stopped"; fi
	@if [ -f $(UI_PID) ] && kill -0 $$(cat $(UI_PID)) 2>/dev/null; then echo "UI running: $$(cat $(UI_PID))"; else echo "UI stopped"; fi
	@echo "Logs: $(API_LOG), $(UI_LOG)"
	@echo "SQLite data is preserved in app/data/agent_flow.sqlite3"

logs:
	@mkdir -p $(RUNTIME_DIR)
	@touch $(API_LOG) $(UI_LOG)
	@tail -n 80 $(API_LOG) $(UI_LOG)

migrate:
	@echo "Applying pending SQLite migrations only..."
	@$(PYTHON) -c "from app.database import migrate; migrate(); print('migrations ok')"
