import * as cdk from 'aws-cdk-lib';
import * as iam from 'aws-cdk-lib/aws-iam';
import { Construct } from 'constructs';

export interface GitHubOidcStackProps extends cdk.StackProps {
  /** owner/repo, e.g. Alex-Minski/triageops */
  readonly githubRepo: string;
}

/**
 * An IAM role GitHub Actions can assume through OpenID Connect. The role can only
 * assume the CDK bootstrap roles, so the workflow deploys exactly what `cdk deploy`
 * would and holds no long-lived keys.
 */
export class GitHubOidcStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: GitHubOidcStackProps) {
    super(scope, id, props);

    const provider = new iam.OpenIdConnectProvider(this, 'GitHubProvider', {
      url: 'https://token.actions.githubusercontent.com',
      clientIds: ['sts.amazonaws.com'],
    });

    const role = new iam.Role(this, 'DeployRole', {
      roleName: 'triageops-github-deploy',
      maxSessionDuration: cdk.Duration.hours(1),
      assumedBy: new iam.WebIdentityPrincipal(provider.openIdConnectProviderArn, {
        StringEquals: { 'token.actions.githubusercontent.com:aud': 'sts.amazonaws.com' },
        StringLike: { 'token.actions.githubusercontent.com:sub': `repo:${props.githubRepo}:ref:refs/heads/main` },
      }),
    });
    role.addToPolicy(new iam.PolicyStatement({
      actions: ['sts:AssumeRole'],
      resources: [`arn:aws:iam::${this.account}:role/cdk-*`],
    }));

    new cdk.CfnOutput(this, 'DeployRoleArn', { value: role.roleArn });
  }
}
