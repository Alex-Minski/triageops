import * as fs from 'fs';
import * as path from 'path';
import * as cdk from 'aws-cdk-lib';
import * as apigw from 'aws-cdk-lib/aws-apigateway';
import * as bedrock from 'aws-cdk-lib/aws-bedrock';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as origins from 'aws-cdk-lib/aws-cloudfront-origins';
import * as cw from 'aws-cdk-lib/aws-cloudwatch';
import * as cwActions from 'aws-cdk-lib/aws-cloudwatch-actions';
import * as cognito from 'aws-cdk-lib/aws-cognito';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as eventSources from 'aws-cdk-lib/aws-lambda-event-sources';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as s3deploy from 'aws-cdk-lib/aws-s3-deployment';
import * as s3vectors from 'aws-cdk-lib/aws-s3vectors';
import * as sns from 'aws-cdk-lib/aws-sns';
import * as subs from 'aws-cdk-lib/aws-sns-subscriptions';
import * as sqs from 'aws-cdk-lib/aws-sqs';
import * as sfn from 'aws-cdk-lib/aws-stepfunctions';
import * as tasks from 'aws-cdk-lib/aws-stepfunctions-tasks';
import { Construct } from 'constructs';

export interface TriageOpsStackProps extends cdk.StackProps {
  readonly classifyModelId: string;
  readonly draftModelId: string;
  readonly embedModelId: string;
  readonly confidenceThreshold: string;
  readonly duplicateThreshold: string;
  readonly promptCache: boolean;
  readonly alarmEmail?: string;
}

const ROOT = path.join(__dirname, '..', '..');
const EMBED_DIMENSIONS = 1024; // must match backend/src/triageops/dedupe.py

export class TriageOpsStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: TriageOpsStackProps) {
    super(scope, id, props);

    // ---------------------------------------------------------------- storage
    const table = new dynamodb.TableV2(this, 'Tickets', {
      partitionKey: { name: 'ticketId', type: dynamodb.AttributeType.STRING },
      billing: dynamodb.Billing.onDemand(),
      pointInTimeRecoverySpecification: { pointInTimeRecoveryEnabled: true },
      globalSecondaryIndexes: [{
        indexName: 'byStatus',
        partitionKey: { name: 'status', type: dynamodb.AttributeType.STRING },
        sortKey: { name: 'createdAt', type: dynamodb.AttributeType.STRING },
      }],
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // Raw ticket text can contain PII: KMS-encrypted, private, deleted after 30 days.
    const rawBucket = new s3.Bucket(this, 'RawTickets', {
      encryption: s3.BucketEncryption.KMS_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      enforceSSL: true,
      lifecycleRules: [{ prefix: 'raw/', expiration: cdk.Duration.days(30) }],
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    const runbookBucket = new s3.Bucket(this, 'Runbooks', {
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      enforceSSL: true,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });
    new s3deploy.BucketDeployment(this, 'DeployRunbooks', {
      sources: [s3deploy.Source.asset(path.join(ROOT, 'runbooks'))],
      destinationBucket: runbookBucket,
    });

    // ---------------------------------------------------------- vector store
    const vectorBucketName = `triageops-vectors-${this.account}-${this.region}`;
    const vectorBucket = new s3vectors.CfnVectorBucket(this, 'VectorBucket', { vectorBucketName });
    const runbookIndex = new s3vectors.CfnIndex(this, 'RunbookIndex', {
      vectorBucketArn: vectorBucket.attrVectorBucketArn,
      indexName: 'runbooks',
      dataType: 'float32',
      dimension: EMBED_DIMENSIONS,
      distanceMetric: 'cosine',
      // Bedrock stores chunk text in these keys; they must be non-filterable.
      metadataConfiguration: { nonFilterableMetadataKeys: ['AMAZON_BEDROCK_TEXT', 'AMAZON_BEDROCK_METADATA'] },
    });
    const ticketIndex = new s3vectors.CfnIndex(this, 'TicketIndex', {
      vectorBucketArn: vectorBucket.attrVectorBucketArn,
      indexName: 'tickets',
      dataType: 'float32',
      dimension: EMBED_DIMENSIONS,
      distanceMetric: 'cosine',
    });

    // -------------------------------------------------------- knowledge base
    const embedModelArn = `arn:aws:bedrock:${this.region}::foundation-model/${props.embedModelId}`;
    const kbRole = new iam.Role(this, 'KnowledgeBaseRole', {
      assumedBy: new iam.ServicePrincipal('bedrock.amazonaws.com', {
        conditions: { StringEquals: { 'aws:SourceAccount': this.account } },
      }),
    });
    runbookBucket.grantRead(kbRole);
    kbRole.addToPolicy(new iam.PolicyStatement({ actions: ['bedrock:InvokeModel'], resources: [embedModelArn] }));
    kbRole.addToPolicy(new iam.PolicyStatement({
      actions: ['s3vectors:PutVectors', 's3vectors:GetVectors', 's3vectors:DeleteVectors',
        's3vectors:QueryVectors', 's3vectors:GetIndex'],
      resources: [runbookIndex.attrIndexArn],
    }));

    const kb = new bedrock.CfnKnowledgeBase(this, 'RunbookKnowledgeBase', {
      name: `${this.stackName}-runbooks`,
      roleArn: kbRole.roleArn,
      knowledgeBaseConfiguration: {
        type: 'VECTOR',
        vectorKnowledgeBaseConfiguration: {
          embeddingModelArn: embedModelArn,
          embeddingModelConfiguration: {
            bedrockEmbeddingModelConfiguration: { dimensions: EMBED_DIMENSIONS, embeddingDataType: 'FLOAT32' },
          },
        },
      },
      storageConfiguration: {
        type: 'S3_VECTORS',
        s3VectorsConfiguration: { indexArn: runbookIndex.attrIndexArn },
      },
    });
    kb.node.addDependency(kbRole);

    const dataSource = new bedrock.CfnDataSource(this, 'RunbookDataSource', {
      knowledgeBaseId: kb.attrKnowledgeBaseId,
      name: 'runbooks-s3',
      dataSourceConfiguration: { type: 'S3', s3Configuration: { bucketArn: runbookBucket.bucketArn } },
      vectorIngestionConfiguration: {
        chunkingConfiguration: {
          chunkingStrategy: 'FIXED_SIZE',
          fixedSizeChunkingConfiguration: { maxTokens: 300, overlapPercentage: 15 },
        },
      },
    });

    // ------------------------------------------------------------- guardrail
    const piiTypes = ['EMAIL', 'PHONE', 'NAME', 'ADDRESS', 'IP_ADDRESS', 'MAC_ADDRESS', 'PASSWORD',
      'CREDIT_DEBIT_CARD_NUMBER', 'US_SOCIAL_SECURITY_NUMBER', 'CA_SOCIAL_INSURANCE_NUMBER',
      'CA_HEALTH_NUMBER', 'AWS_ACCESS_KEY', 'AWS_SECRET_KEY'];
    const guardrail = new bedrock.CfnGuardrail(this, 'TicketGuardrail', {
      name: `${this.stackName}-tickets`,
      description: 'Masks PII in tickets and detects prompt-injection attempts',
      blockedInputMessaging: 'This ticket was blocked by the input guardrail.',
      blockedOutputsMessaging: 'The response was blocked by the output guardrail.',
      sensitiveInformationPolicyConfig: {
        piiEntitiesConfig: piiTypes.map((type) => ({ type, action: 'ANONYMIZE' })),
      },
      contentPolicyConfig: {
        // Detect-only (inputAction NONE): we flag the ticket for human review instead of
        // dropping it, because a real outage report can look like an injection.
        filtersConfig: [{ type: 'PROMPT_ATTACK', inputStrength: 'HIGH', outputStrength: 'NONE', inputAction: 'NONE' }],
      },
    });
    const guardrailVersion = new bedrock.CfnGuardrailVersion(this, 'TicketGuardrailVersion', {
      guardrailIdentifier: guardrail.attrGuardrailId,
      description: 'v1',
    });

    // ------------------------------------------------------------- functions
    const layer = new lambda.LayerVersion(this, 'Deps', {
      code: lambda.Code.fromAsset(path.join(ROOT, 'build', 'layer')),
      compatibleRuntimes: [lambda.Runtime.PYTHON_3_13],
      compatibleArchitectures: [lambda.Architecture.ARM_64],
      description: 'boto3 + pydantic (built by `make layer`)',
    });
    const code = lambda.Code.fromAsset(path.join(ROOT, 'backend', 'src'), {
      exclude: ['**/__pycache__', '**/*.pyc'],
    });

    const queue = new sqs.Queue(this, 'TriageQueue', {
      visibilityTimeout: cdk.Duration.seconds(180),
      enforceSSL: true,
      deadLetterQueue: {
        maxReceiveCount: 3,
        queue: new sqs.Queue(this, 'TriageDLQ', { retentionPeriod: cdk.Duration.days(14), enforceSSL: true }),
      },
    });
    const dlq = queue.deadLetterQueue!.queue;

    const baseEnv: Record<string, string> = {
      TABLE_NAME: table.tableName,
      RAW_BUCKET: rawBucket.bucketName,
      GUARDRAIL_ID: guardrail.attrGuardrailId,
      GUARDRAIL_VERSION: guardrailVersion.attrVersion,
      CLASSIFY_MODEL_ID: props.classifyModelId,
      DRAFT_MODEL_ID: props.draftModelId,
      EMBED_MODEL_ID: props.embedModelId,
      VECTOR_BUCKET: vectorBucketName,
      TICKET_INDEX: 'tickets',
      KB_ID: kb.attrKnowledgeBaseId,
      CONFIDENCE_THRESHOLD: props.confidenceThreshold,
      DUPLICATE_THRESHOLD: props.duplicateThreshold,
      PROMPT_CACHE: String(props.promptCache),
    };

    const fn = (name: string, handler: string, timeoutSec = 30, memory = 512) => {
      const logGroup = new logs.LogGroup(this, `${name}Logs`, {
        retention: logs.RetentionDays.TWO_WEEKS,
        removalPolicy: cdk.RemovalPolicy.DESTROY,
      });
      return new lambda.Function(this, name, {
        runtime: lambda.Runtime.PYTHON_3_13,
        architecture: lambda.Architecture.ARM_64, // Graviton: cheaper per GB-second
        handler,
        code,
        layers: [layer],
        memorySize: memory,
        timeout: cdk.Duration.seconds(timeoutSec),
        tracing: lambda.Tracing.ACTIVE,
        environment: baseEnv,
        logGroup,
      });
    };

    const ingestFn = fn('IngestFn', 'handlers.ingest.handler', 10);
    ingestFn.addEnvironment('QUEUE_URL', queue.queueUrl);
    rawBucket.grantPut(ingestFn);
    table.grantWriteData(ingestFn);
    queue.grantSendMessages(ingestFn);

    const apiFn = fn('ApiFn', 'handlers.api.handler', 15);
    table.grantReadWriteData(apiFn);

    const maskFn = fn('MaskFn', 'handlers.steps.mask_handler');
    rawBucket.grantRead(maskFn);
    table.grantReadWriteData(maskFn);
    maskFn.addToRolePolicy(new iam.PolicyStatement({
      actions: ['bedrock:ApplyGuardrail'],
      resources: [guardrail.attrGuardrailArn],
    }));

    const classifyFn = fn('ClassifyFn', 'handlers.steps.classify_handler', 60);
    classifyFn.addToRolePolicy(this.invokeModelPolicy(props.classifyModelId));

    const duplicatesFn = fn('DuplicatesFn', 'handlers.steps.duplicates_handler', 30);
    duplicatesFn.addToRolePolicy(this.invokeModelPolicy(props.embedModelId));
    duplicatesFn.addToRolePolicy(new iam.PolicyStatement({
      actions: ['s3vectors:QueryVectors', 's3vectors:PutVectors', 's3vectors:GetVectors'],
      resources: [ticketIndex.attrIndexArn],
    }));

    const draftFn = fn('DraftFn', 'handlers.steps.draft_handler', 90);
    draftFn.addToRolePolicy(this.invokeModelPolicy(props.draftModelId));
    draftFn.addToRolePolicy(new iam.PolicyStatement({
      actions: ['bedrock:Retrieve'],
      resources: [kb.attrKnowledgeBaseArn],
    }));

    const finalizeFn = fn('FinalizeFn', 'handlers.steps.finalize_handler');
    table.grantReadWriteData(finalizeFn);
    const failFn = fn('FailFn', 'handlers.steps.fail_handler');
    table.grantReadWriteData(failFn);

    // --------------------------------------------------------- state machine
    const failTask = new tasks.LambdaInvoke(this, 'MarkFailed', { lambdaFunction: failFn, payloadResponseOnly: true });
    const step = (id: string, f: lambda.IFunction, resultPath: string) => {
      const t = new tasks.LambdaInvoke(this, id, { lambdaFunction: f, payloadResponseOnly: true, resultPath });
      // Bedrock throttling surfaces as ClientError; botocore already retries, this is the outer backstop.
      t.addRetry({
        errors: ['ClientError', 'ThrottlingException', 'Lambda.TooManyRequestsException', 'States.Timeout'],
        interval: cdk.Duration.seconds(2), maxAttempts: 3, backoffRate: 2, jitterStrategy: sfn.JitterType.FULL,
      });
      t.addCatch(failTask, { resultPath: '$.error' });
      return t;
    };
    const definition = step('MaskPII', maskFn, '$.mask')
      .next(step('Classify', classifyFn, '$.classification'))
      .next(step('FindDuplicates', duplicatesFn, '$.duplicates'))
      .next(step('DraftFix', draftFn, '$.draft'))
      .next(step('Finalize', finalizeFn, '$.result'));

    const stateMachine = new sfn.StateMachine(this, 'TriageWorkflow', {
      definitionBody: sfn.DefinitionBody.fromChainable(definition),
      stateMachineType: sfn.StateMachineType.STANDARD,
      timeout: cdk.Duration.minutes(5),
      tracingEnabled: true,
      logs: {
        destination: new logs.LogGroup(this, 'WorkflowLogs', {
          retention: logs.RetentionDays.TWO_WEEKS, removalPolicy: cdk.RemovalPolicy.DESTROY,
        }),
        level: sfn.LogLevel.ERROR,
      },
    });

    const starterFn = fn('StarterFn', 'handlers.starter.handler', 30, 256);
    starterFn.addEnvironment('STATE_MACHINE_ARN', stateMachine.stateMachineArn);
    stateMachine.grantStartExecution(starterFn);
    starterFn.addEventSource(new eventSources.SqsEventSource(queue, {
      batchSize: 10,
      reportBatchItemFailures: true,
      maxConcurrency: 5, // throttle valve in front of Bedrock quotas
    }));

    // -------------------------------------------------------------- auth/API
    const userPool = new cognito.UserPool(this, 'Users', {
      selfSignUpEnabled: false,
      signInAliases: { email: true },
      passwordPolicy: { minLength: 12, requireSymbols: false },
      accountRecovery: cognito.AccountRecovery.EMAIL_ONLY,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });
    const userPoolClient = userPool.addClient('WebClient', {
      authFlows: { userPassword: true, userSrp: true },
      generateSecret: false,
      idTokenValidity: cdk.Duration.hours(1),
    });

    const api = new apigw.RestApi(this, 'Api', {
      restApiName: 'triageops',
      deployOptions: {
        stageName: 'v1',
        tracingEnabled: true,
        metricsEnabled: true,
        throttlingRateLimit: 50,
        throttlingBurstLimit: 100,
      },
      defaultCorsPreflightOptions: {
        allowOrigins: apigw.Cors.ALL_ORIGINS,
        allowHeaders: ['Content-Type', 'Authorization', 'X-Api-Key', 'Idempotency-Key'],
        allowMethods: ['GET', 'POST', 'OPTIONS'],
      },
    });
    // Errors raised by API Gateway itself (expired token, throttling) need CORS headers too,
    // or the browser reports a misleading CORS failure instead of the real 401/429.
    for (const type of [apigw.ResponseType.DEFAULT_4XX, apigw.ResponseType.DEFAULT_5XX]) {
      api.addGatewayResponse(`Cors${type.responseType}`, {
        type,
        responseHeaders: {
          'Access-Control-Allow-Origin': "'*'",
          'Access-Control-Allow-Headers': "'Content-Type,Authorization,X-Api-Key,Idempotency-Key'",
        },
      });
    }
    const authorizer = new apigw.CognitoUserPoolsAuthorizer(this, 'Authorizer', { cognitoUserPools: [userPool] });
    const auth = { authorizer, authorizationType: apigw.AuthorizationType.COGNITO };
    const ingest = new apigw.LambdaIntegration(ingestFn);
    const read = new apigw.LambdaIntegration(apiFn);

    const tickets = api.root.addResource('tickets');
    tickets.addMethod('POST', ingest, auth);
    tickets.addMethod('GET', read, auth);
    const ticket = tickets.addResource('{ticketId}');
    ticket.addMethod('GET', read, auth);
    ticket.addResource('review').addMethod('POST', read, auth);
    api.root.addResource('stats').addMethod('GET', read, auth);
    api.root.addResource('webhooks').addResource('alerts').addMethod('POST', ingest, { apiKeyRequired: true });

    const apiKey = api.addApiKey('WebhookKey', { description: 'For alert sources and load tests' });
    const plan = api.addUsagePlan('WebhookPlan', { throttle: { rateLimit: 50, burstLimit: 100 } });
    plan.addApiKey(apiKey);
    plan.addApiStage({ stage: api.deploymentStage });

    // --------------------------------------------------------------- web app
    const siteBucket = new s3.Bucket(this, 'Site', {
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      enforceSSL: true,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });
    const distribution = new cloudfront.Distribution(this, 'SiteCdn', {
      defaultBehavior: {
        origin: origins.S3BucketOrigin.withOriginAccessControl(siteBucket),
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
      },
      defaultRootObject: 'index.html',
      errorResponses: [403, 404].map((httpStatus) => ({
        httpStatus, responseHttpStatus: 200, responsePagePath: '/index.html',
      })),
    });
    const runtimeConfig = s3deploy.Source.jsonData('config.json', {
      apiUrl: api.url,
      region: this.region,
      userPoolId: userPool.userPoolId,
      userPoolClientId: userPoolClient.userPoolClientId,
    });
    const dist = path.join(ROOT, 'frontend', 'dist');
    new s3deploy.BucketDeployment(this, 'DeploySite', {
      sources: fs.existsSync(dist) ? [s3deploy.Source.asset(dist), runtimeConfig] : [runtimeConfig],
      destinationBucket: siteBucket,
      distribution,
      distributionPaths: ['/*'],
    });

    // --------------------------------------------------------- observability
    const alarmTopic = new sns.Topic(this, 'Alarms');
    if (props.alarmEmail) alarmTopic.addSubscription(new subs.EmailSubscription(props.alarmEmail));
    const alarm = (id: string, metric: cw.IMetric, threshold: number, description: string) => {
      const a = new cw.Alarm(this, id, {
        metric, threshold, evaluationPeriods: 1, alarmDescription: description,
        comparisonOperator: cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
        treatMissingData: cw.TreatMissingData.NOT_BREACHING,
      });
      a.addAlarmAction(new cwActions.SnsAction(alarmTopic));
      return a;
    };
    alarm('DlqNotEmpty', dlq.metricApproximateNumberOfMessagesVisible({ period: cdk.Duration.minutes(5) }), 1,
      'Tickets failed to start triage three times and landed in the DLQ');
    alarm('WorkflowFailures', stateMachine.metricFailed({ period: cdk.Duration.minutes(5) }), 1,
      'A triage workflow execution failed');
    alarm('Api5xx', api.metricServerError({ period: cdk.Duration.minutes(5) }), 5, 'API is returning 5XX errors');

    const custom = (metricName: string, statistic = 'Sum') =>
      new cw.Metric({ namespace: 'TriageOps', metricName, statistic, period: cdk.Duration.minutes(5) });
    new cw.Dashboard(this, 'Dashboard', {
      dashboardName: 'TriageOps',
      widgets: [
        [
          new cw.GraphWidget({ title: 'Tickets', left: [custom('TicketsReceived'), custom('TicketsTriaged'), custom('NeedsReview'), custom('TicketsFailed')] }),
          new cw.GraphWidget({ title: 'End-to-end latency (ms)', left: [custom('EndToEndLatencyMs', 'p50'), custom('EndToEndLatencyMs', 'p95')] }),
        ],
        [
          new cw.GraphWidget({ title: 'Bedrock cost (USD, estimated)', left: [custom('CostUsd')] }),
          new cw.GraphWidget({ title: 'Queue depth', left: [queue.metricApproximateNumberOfMessagesVisible(), dlq.metricApproximateNumberOfMessagesVisible()] }),
          new cw.GraphWidget({ title: 'Classifier confidence', left: [custom('Confidence', 'Average')] }),
        ],
      ],
    });

    // --------------------------------------------------------------- outputs
    const out = (id: string, value: string) => new cdk.CfnOutput(this, id, { value });
    out('ApiUrl', api.url);
    out('WebAppUrl', `https://${distribution.distributionDomainName}`);
    out('UserPoolId', userPool.userPoolId);
    out('UserPoolClientId', userPoolClient.userPoolClientId);
    out('WebhookApiKeyId', apiKey.keyId);
    out('KnowledgeBaseId', kb.attrKnowledgeBaseId);
    out('DataSourceId', dataSource.attrDataSourceId);
    out('GuardrailId', guardrail.attrGuardrailId);
    out('GuardrailVersion', guardrailVersion.attrVersion);
    out('VectorBucketName', vectorBucketName);
    out('TableName', table.tableName);
    out('StateMachineArn', stateMachine.stateMachineArn);
  }

  /** Permission to call a model directly or through a cross-region inference profile. */
  private invokeModelPolicy(modelId: string): iam.PolicyStatement {
    const profile = modelId.match(/^(us|eu|apac|ca|global)\.(.+)$/);
    const resources = profile
      ? [
          `arn:aws:bedrock:${this.region}:${this.account}:inference-profile/${modelId}`,
          `arn:aws:bedrock:*::foundation-model/${profile[2]}`,
        ]
      : [`arn:aws:bedrock:${this.region}::foundation-model/${modelId}`];
    return new iam.PolicyStatement({ actions: ['bedrock:InvokeModel'], resources });
  }
}
