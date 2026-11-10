#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { TriageOpsStack } from '../lib/triageops-stack';
import { GitHubOidcStack } from '../lib/github-oidc-stack';

const app = new cdk.App();
const env = {
  account: process.env.CDK_DEFAULT_ACCOUNT,
  region: process.env.CDK_DEFAULT_REGION ?? 'us-east-1',
};
const ctx = (key: string) => String(app.node.tryGetContext(key) ?? '');

new TriageOpsStack(app, 'TriageOps', {
  env,
  description: 'TriageOps: AI triage for IT tickets and security alerts on Amazon Bedrock',
  classifyModelId: ctx('classifyModelId'),
  draftModelId: ctx('draftModelId'),
  embedModelId: ctx('embedModelId'),
  confidenceThreshold: ctx('confidenceThreshold'),
  duplicateThreshold: ctx('duplicateThreshold'),
  promptCache: ctx('promptCache') === 'true',
  alarmEmail: ctx('alarmEmail') || undefined,
});

// Optional: lets GitHub Actions deploy with short-lived credentials (no stored AWS keys).
// Deploy once with: npx cdk deploy TriageOpsGitHubOidc -c githubRepo=<owner>/<repo>
if (ctx('githubRepo')) {
  new GitHubOidcStack(app, 'TriageOpsGitHubOidc', { env, githubRepo: ctx('githubRepo') });
}

cdk.Tags.of(app).add('project', 'triageops');
