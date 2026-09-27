# The interface to this repository. `make help` lists every target.
# Deployment targets take their values explicitly and pass --project and
# --region to every gcloud call, so nothing runs against an ambient default.

.PHONY: help setup install hooks run clean format lint typecheck test infra-test check \
        docker-build docker-smoke image infra-init infra-plan infra-apply verify proxy \
        require-project require-tfvars require-backend require-clean

PREFIX ?= email-agent
IMAGE_NAME := email-assistance-agent
TOFU := tofu -chdir=infra

help: ## List the targets
	@grep -hE '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  %-14s %s\n", $$1, $$2}'

# ---- Development ------------------------------------------------------------

setup: ## Install dependencies and git hooks
	uv sync
	$(MAKE) hooks

install: setup ## Alias for setup

hooks: ## Install the pre-commit, commit-msg and pre-push hooks
	uv run pre-commit install --install-hooks

run: ## Serve MCP at http://localhost:8080/mcp (needs .env with a test mailbox)
	uv run email-assistance-agent

clean: ## Remove local caches and the virtualenv
	rm -rf .venv .mypy_cache .pytest_cache .ruff_cache .coverage htmlcov infra/.terraform
	find . -type d -name __pycache__ -prune -exec rm -rf {} +

format: ## Fix formatting and autofixable lint
	uv run ruff format .
	uv run ruff check --fix .
	tofu fmt -recursive infra

lint: ## Check formatting and lint, Python and OpenTofu
	uv run ruff format --check .
	uv run ruff check .
	tofu fmt -check -recursive infra

typecheck: ## mypy, strict
	uv run mypy

test: ## pytest with coverage (80% minimum)
	uv run pytest

infra-test: ## Validate the OpenTofu and run its offline tests
	$(TOFU) init -backend=false -input=false >/dev/null
	$(TOFU) validate
	$(TOFU) test

check: lint typecheck test infra-test ## Exactly what CI runs
	@echo "check passed"

docker-build: ## Build the image locally
	docker build --tag $(IMAGE_NAME):local .

docker-smoke: ## Build the image and check it serves exactly the five tools
	scripts/docker-smoke.sh

# ---- Deployment (see AGENTS.md, section A) ----------------------------------

require-project:
	@test -n "$(PROJECT)" || { echo "Set PROJECT=<gcp-project-id>"; exit 1; }
	@test -n "$(REGION)" || { echo "Set REGION=<region>, e.g. europe-west6"; exit 1; }

require-tfvars:
	@test -n "$(TFVARS)" && test -f "$(TFVARS)" || { echo "Set TFVARS=<path to your email-assistance-agent.tfvars>"; exit 1; }

require-backend:
	@test -n "$(BACKEND)" && test -f "$(BACKEND)" || { echo "Set BACKEND=<path to your backend.hcl>"; exit 1; }

require-clean:
	@test -z "$$(git status --porcelain)" || { echo "Commit or stash changes first: the image is tagged with the commit."; exit 1; }

image: require-project require-clean ## Build with Cloud Build; prints the digest for tfvars (PROJECT, REGION)
	$(eval REPO := $(REGION)-docker.pkg.dev/$(PROJECT)/$(PREFIX))
	$(eval TAG := $(REPO)/$(IMAGE_NAME):$(shell git rev-parse --short=12 HEAD))
	gcloud builds submit --project "$(PROJECT)" --region "$(REGION)" --tag "$(TAG)" \
	  --service-account "projects/$(PROJECT)/serviceAccounts/$(PREFIX)-build@$(PROJECT).iam.gserviceaccount.com" \
	  --gcs-source-staging-dir "gs://$(PROJECT)-$(PREFIX)-build/source" \
	  --gcs-log-dir "gs://$(PROJECT)-$(PREFIX)-build/logs" .
	@echo "image = \"$(REPO)/$(IMAGE_NAME)@$$(gcloud artifacts docker images describe "$(TAG)" --project "$(PROJECT)" --format='value(image_summary.digest)')\""

infra-init: require-backend ## tofu init with your backend config (BACKEND)
	$(TOFU) init -input=false -backend-config="$(abspath $(BACKEND))"

infra-plan: require-tfvars ## tofu plan with your values, saved for apply (TFVARS)
	$(TOFU) plan -input=false -var-file="$(abspath $(TFVARS))" -out=tfplan

infra-apply: require-tfvars ## Apply exactly the saved plan (TFVARS)
	$(TOFU) apply -input=false tfplan

verify: require-project ## Fail unless SMTP is blocked and IMAP open from the service network (PROJECT, REGION)
	gcloud run jobs execute "$(PREFIX)-egress-check" --project "$(PROJECT)" --region "$(REGION)" --wait

proxy: require-project ## Connect localhost:8080 to one mailbox's service (PROJECT, REGION, MAILBOX)
	@test -n "$(MAILBOX)" || { echo "Set MAILBOX=<key from your mailboxes map>"; exit 1; }
	gcloud run services proxy "$(PREFIX)-$(MAILBOX)" --project "$(PROJECT)" --region "$(REGION)" --port 8080
