PYTHON ?= python3

.PHONY: verify review-staged
verify:
	$(PYTHON) -m pytest -q
	$(PYTHON) -m ruff check .
	$(PYTHON) -m delivery_kit.governance
	@for script in scripts/*.sh; do bash -n "$$script" || exit; done
	@if command -v shellcheck >/dev/null 2>&1; then shellcheck scripts/*.sh; else printf '%s\n' 'ShellCheck unavailable, syntax gate only'; fi

review-staged:
	git diff --cached --check
	git diff --cached --stat
	@printf '%s\n' 'Required evidence: make verify, synthetic navigation baseline, publication files and history scan'
