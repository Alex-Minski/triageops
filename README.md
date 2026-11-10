# TriageOps

AI triage for IT support tickets and security alerts, built serverless on AWS with Amazon Bedrock.

Each ticket gets its personal data masked, a category, priority and owning team, a check for duplicates of past tickets, and a drafted fix with citations to the team's runbooks. Anything the model is unsure about, or that looks like a prompt-injection attempt, goes to a human review queue. Every correction made there is saved and can be exported to grow the evaluation set.

![Ticket detail: masked text, model triage, cited fix and review form](docs/ticket-demo.png)
<sub>Screenshot from demo mode (sample data).</sub>

```mermaid
flowchart TB
  web[React web app<br/>S3 + CloudFront, Cognito] --> apigw[API Gateway]
  alerts[Alert webhooks<br/>API key] --> apigw
  apigw --> ingest[Ingest Lambda] --> sqs[(SQS + DLQ)]
  ingest --> raw[(Raw bucket<br/>KMS, 30-day expiry)]
  sqs --> starter[Starter Lambda<br/>max concurrency 5] --> sfn
  subgraph sfn[Step Functions triage workflow]
    mask[1. Mask PII<br/>Bedrock Guardrails] --> cls[2. Classify<br/>Converse + forced tool] --> dup[3. Duplicates<br/>Titan embeddings + S3 Vectors] --> draft[4. Draft fix<br/>Knowledge Base on S3 Vectors] --> fin[Finalize]
  end
  fin --> ddb[(DynamoDB)]
  apigw --> apiFn[API Lambda] --> ddb
```

## What's in the repo

| Path | What it is |
| --- | --- |
| `backend/src/triageops/` | Shared Python package: models, classifier, guardrails, dedupe, drafter, pricing, storage |
| `backend/src/handlers/` | Lambda entry points: ingest, starter, the five workflow steps, read/review API |
| `backend/tests/` | 24 unit tests (Bedrock faked, DynamoDB/S3/SQS mocked with moto) |
| `infra/` | AWS CDK app in TypeScript, plus 6 assertion tests |
| `frontend/` | React + TypeScript web app (Vite) |
| `eval/` | Baseline, LLM evaluation, duplicate-threshold tuning, red-team tests, synthetic data |
| `runbooks/` | 21 runbooks the Knowledge Base indexes |
| `scripts/` | Create users, sync the Knowledge Base, seed tickets, check load-test runs, export reviews |
| `loadtest/` | k6 load test for the webhook |

## Prerequisites

- An AWS account with the AWS CLI configured (`aws sts get-caller-identity` works). Use `us-east-1`: it has every service used here.
- Bedrock access in `us-east-1` to **Amazon Nova Lite**, **Amazon Nova Pro** and **Titan Text Embeddings V2**. Check this in the Bedrock console's model catalog before deploying.
- Node.js 22 and Python 3.13.
- An AWS Budgets alert (e.g. $10 a month) set up *before* you deploy.

## Deploy

```bash
make install                         # Python dev deps, CDK, frontend packages
cd infra && npx cdk bootstrap && cd ..   # once per account/region
make deploy                          # builds the layer + web app, deploys, writes build/outputs.json
make sync-kb                         # indexes the runbooks into the Knowledge Base
python scripts/create_user.py you@example.com 'a-long-password-here'
make seed                            # sends 50 test tickets through the webhook
```

Open the `WebAppUrl` from `build/outputs.json` and sign in. Edit a runbook? Run `make sync-kb` again.

**See the UI without AWS:** `cd frontend && npm run dev`, then open <http://localhost:5173/?demo>. Demo mode uses sample data and says so in the sidebar.

## Evaluate

```bash
python eval/baseline.py                                   # TF-IDF + logistic regression: the bar to beat
python eval/run_eval.py --limit 50                        # cheap smoke run on Bedrock
python eval/run_eval.py                                   # full test split
python eval/run_eval.py --model us.amazon.nova-micro-v1:0 # compare a cheaper model
python eval/run_eval.py --prompt-cache                    # measure prompt caching
python eval/dedupe_eval.py                                # pick the duplicate threshold
python eval/guardrail_eval.py --guardrail-id <GuardrailId> --guardrail-version <GuardrailVersion>
```

Every run writes a JSON file and appends a row to `eval/results/RESULTS.md` with the date and git commit, so every reported number traces back to a reproducible run.

**Use real data for the numbers you quote.** The bundled synthetic tickets come from templates and are far easier than real ones: the baseline scores about 99% on category. They prove the pipeline works, nothing more. For real numbers, download a public labeled IT-ticket dataset (Kaggle and Hugging Face both have several), map its labels in a copy of `eval/label_map.example.json`, then:

```bash
python eval/prepare_data.py --input your_dataset.csv --title-col <col> --body-col <col> \
  --category-col <col> --priority-col <col> --label-map eval/my_label_map.json --force
```

The test split is locked after that. Do prompt experiments with `--split val` only.

## Load test

```bash
KEY=$(aws apigateway get-api-key --api-key <WebhookApiKeyId> --include-value --query value --output text)
k6 run -e API_URL=<ApiUrl> -e API_KEY=$KEY -e RATE=60 -e DURATION=5m loadtest/webhook.js
python scripts/check_run.py --since <start time k6 printed>
```

Step `RATE` up (60, 120, 240 a minute) until tickets start backing up in the queue. Bedrock quotas set the ceiling, not Lambda. The starter's maximum concurrency is the valve: raise it in `infra/lib/triageops-stack.ts` only if your quotas allow.

## Configuration

Change these in `infra/cdk.json` or pass them with `-c` to `cdk deploy`:

| Key | Default | Notes |
| --- | --- | --- |
| `classifyModelId` | `us.amazon.nova-lite-v1:0` | Any Converse model that supports tool use. Copy the exact ID or inference profile from the Bedrock console. |
| `draftModelId` | `us.amazon.nova-pro-v1:0` | Larger model, used only for drafting fixes |
| `embedModelId` | `amazon.titan-embed-text-v2:0` | 1,024 dimensions. Changing the model means rebuilding both vector indexes. |
| `confidenceThreshold` | `0.7` | Below this, a ticket goes to review. Choose it from the `autoTriageShare` and `autoTriageJointAccuracy` metrics. |
| `duplicateThreshold` | `0.85` | Set it from `eval/dedupe_eval.py` |
| `promptCache` | `false` | Adds a cache point after the system prompt |
| `alarmEmail` | empty | Subscribes an email address to the alarms |

Prices used for cost estimates are in `backend/src/triageops/prices.json`. **Check them against the [Bedrock pricing page](https://aws.amazon.com/bedrock/pricing/) before you quote a cost.**

## Design decisions

| Decision | Why |
| --- | --- |
| SQS between the API and the workflow | Absorbs alert storms, retries failures, and dead-letters poison messages. Callers get a 202 in milliseconds. |
| Deterministic IDs and conditional writes | A retried webhook can't create a second ticket: the alert ID hashes to the same ticket ID, `attribute_not_exists` guards the write, and the execution name blocks a second workflow run. |
| Step Functions, not an agent | The steps are known in advance, so a fixed workflow is cheaper, testable, and every run is visible in the console. |
| Forced tool call + Pydantic | The model can only fill in a schema. Invalid output gets one retry, then goes to human review. |
| Guardrail prompt-attack filter in detect-only mode | A real outage report can look like an injection, so suspect tickets go to a human instead of being dropped. |
| Raw text only in S3; DynamoDB holds masked text | The UI and the model never see PII. Raw copies expire after 30 days. |
| S3 Vectors for both indexes | Far cheaper than OpenSearch Serverless at this scale. The trade-off: semantic search only, and slower queries. |
| Graviton (arm64) Lambdas, layer built without Docker | Cheaper per GB-second, and `make layer` cross-installs arm64 wheels. |

## Costs and teardown

While idle, the stack costs close to nothing (S3, DynamoDB on-demand, and CloudWatch logs with 14-day retention). Bedrock tokens are the main cost when it runs. Full evaluations and load tests cost money each time, so run them deliberately. When you're done for a while:

```bash
make destroy
```

## CI/CD

`.github/workflows/ci.yml` runs the backend tests, the baseline, the CDK assertion tests and synth, and the frontend build on every push. `deploy.yml` deploys on manual dispatch using GitHub OIDC, with no AWS keys stored in GitHub. One-time setup:

```bash
cd infra && npx cdk deploy TriageOpsGitHubOidc -c githubRepo=<owner>/<repo>
# add the DeployRoleArn output as the repo secret AWS_DEPLOY_ROLE_ARN
```

## Troubleshooting

- **`AccessDeniedException` on InvokeModel:** your account doesn't have access to that model in this region yet, or the model ID is wrong. Check the Bedrock console.
- **Tickets stuck in `triaging`:** open the execution in the Step Functions console. Throttling retries show up there.
- **Draft says "No matching runbook" for everything:** you haven't run `make sync-kb` yet.
- **`ValidationException` mentioning an inference profile:** use the `us.` inference-profile ID shown in the console, not the bare model ID.

## Not built yet

- An "ask about this ticket" chat agent on Bedrock AgentCore Runtime. It would call the existing data through AgentCore Gateway tools.
- Email intake through SES (the ingest Lambda already accepts `source: "email"`).
