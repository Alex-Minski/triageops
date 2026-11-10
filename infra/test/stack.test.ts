import * as cdk from 'aws-cdk-lib';
import { Match, Template } from 'aws-cdk-lib/assertions';
import { TriageOpsStack } from '../lib/triageops-stack';

const template = Template.fromStack(new TriageOpsStack(new cdk.App(), 'Test', {
  env: { account: '123456789012', region: 'us-east-1' },
  classifyModelId: 'us.amazon.nova-lite-v1:0',
  draftModelId: 'us.amazon.nova-pro-v1:0',
  embedModelId: 'amazon.titan-embed-text-v2:0',
  confidenceThreshold: '0.7',
  duplicateThreshold: '0.85',
  promptCache: false,
}));

test('knowledge base stores vectors in S3 Vectors', () => {
  template.hasResourceProperties('AWS::Bedrock::KnowledgeBase', {
    StorageConfiguration: { Type: 'S3_VECTORS' },
  });
  template.resourceCountIs('AWS::S3Vectors::Index', 2);
});

test('guardrail anonymizes PII and only detects prompt attacks', () => {
  template.hasResourceProperties('AWS::Bedrock::Guardrail', {
    SensitiveInformationPolicyConfig: {
      PiiEntitiesConfig: Match.arrayWith([{ Type: 'EMAIL', Action: 'ANONYMIZE' }]),
    },
    ContentPolicyConfig: {
      FiltersConfig: [Match.objectLike({ Type: 'PROMPT_ATTACK', InputAction: 'NONE' })],
    },
  });
});

test('queue has a dead-letter queue and the starter is concurrency-capped', () => {
  template.hasResourceProperties('AWS::SQS::Queue', {
    RedrivePolicy: Match.objectLike({ maxReceiveCount: 3 }),
  });
  template.hasResourceProperties('AWS::Lambda::EventSourceMapping', {
    ScalingConfig: { MaximumConcurrency: 5 },
    FunctionResponseTypes: ['ReportBatchItemFailures'],
  });
});

test('every function runs on Graviton with X-Ray tracing', () => {
  const fns = Object.values(template.findResources('AWS::Lambda::Function'))
    .filter((f) => String(f.Properties.Handler).startsWith('handlers.'));
  expect(fns.length).toBe(9);
  for (const f of fns) {
    expect(f.Properties.Architectures).toEqual(['arm64']);
    expect(f.Properties.TracingConfig).toEqual({ Mode: 'Active' });
  }
});

test('webhook route needs an API key; app routes need Cognito', () => {
  template.hasResourceProperties('AWS::ApiGateway::Method', { HttpMethod: 'POST', ApiKeyRequired: true });
  template.hasResourceProperties('AWS::ApiGateway::Method', { HttpMethod: 'GET', AuthorizationType: 'COGNITO_USER_POOLS' });
});

test('raw ticket bucket is KMS-encrypted and expires objects', () => {
  template.hasResourceProperties('AWS::S3::Bucket', {
    BucketEncryption: { ServerSideEncryptionConfiguration: [{ ServerSideEncryptionByDefault: { SSEAlgorithm: 'aws:kms' } }] },
    LifecycleConfiguration: { Rules: [Match.objectLike({ ExpirationInDays: 30, Prefix: 'raw/' })] },
  });
});
