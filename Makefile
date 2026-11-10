# TriageOps developer commands. Run `make help` for the list.
PY ?= python3
LAYER_DIR := build/layer/python

.PHONY: help install layer test test-infra frontend synth deploy sync-kb seed eval baseline destroy clean

help:
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "  %-12s %s\n", $$1, $$2}'

install: ## Install Python dev deps, CDK and frontend packages
	$(PY) -m pip install -r backend/requirements-dev.txt
	cd infra && npm ci
	cd frontend && npm ci

layer: ## Build the Lambda dependency layer for arm64 (no Docker needed)
	rm -rf build/layer && mkdir -p $(LAYER_DIR)
	$(PY) -m pip install -r backend/requirements.txt --target $(LAYER_DIR) \
		--platform manylinux2014_aarch64 --python-version 3.13 --implementation cp \
		--only-binary=:all: --upgrade --quiet

test: ## Run backend unit tests
	cd backend && $(PY) -m pytest -q

test-infra: layer ## Run CDK assertion tests
	cd infra && npx jest

frontend: ## Build the React app into frontend/dist
	cd frontend && npm run build

synth: layer frontend ## Synthesize CloudFormation
	cd infra && npx cdk synth TriageOps > /dev/null && echo "synth OK"

deploy: layer frontend ## Deploy everything to your AWS account
	cd infra && npx cdk deploy TriageOps --outputs-file ../build/outputs.json

sync-kb: ## Index the runbooks into the Knowledge Base (run after deploy and after editing runbooks)
	$(PY) scripts/sync_kb.py

seed: ## Send 50 sample tickets through the deployed API
	$(PY) scripts/seed.py --count 50

baseline: ## Train and score the TF-IDF baseline
	$(PY) eval/baseline.py

eval: ## Run the LLM evaluation on the test split (calls Bedrock, costs a little)
	$(PY) eval/run_eval.py

destroy: ## Delete the stack and stop all charges
	cd infra && npx cdk destroy TriageOps

clean:
	rm -rf build infra/cdk.out frontend/dist
