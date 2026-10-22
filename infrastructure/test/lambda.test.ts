import { Match } from 'aws-cdk-lib/assertions'
import type { Asset } from 'aws-cdk-lib/aws-s3-assets'
import { readdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { foundation } from './helpers.js'

describe('FastAPI Lambda and logging', () => {
  it('excludes developer data, credentials and coverage artifacts from the staged asset', () => {
    const { app, stack, template } = foundation()
    template.resourceCountIs('AWS::Lambda::Function', 4)
    const asset = stack.backend.handler.node.findChild('Code') as Asset
    const names = readdirSync(resolve(app.synth().directory, asset.assetPath))
    expect(names).toContain('app')
    expect(names.filter(name => name.startsWith('.env') || name.startsWith('.coverage') || ['coverage', 'htmlcov'].includes(name))).toEqual([])
    expect(names).not.toContain('data')
    expect(names).not.toContain('.venv')
    expect(names).not.toContain('tests')
  })
  it('uses the shared Python handler and resource references with bounded compute', () => {
    const { template } = foundation()
    template.resourceCountIs('AWS::Lambda::Function', 4)
    template.hasResourceProperties('AWS::Lambda::Function', {
      Runtime: 'python3.13', Architectures: ['x86_64'], MemorySize: 256, Timeout: 15,
      Handler: 'app.lambda_handler.handler', VpcConfig: Match.absent(), Layers: Match.absent(),
      Environment: { Variables: Match.objectLike({
        APP_NAME: 'CivicLens', APP_ENV: 'aws', AUTH_PROVIDER: 'cognito', DEPLOYMENT_STAGE: 'demo', DEBUG: 'false', LOG_LEVEL: 'INFO',
        CORS_ORIGINS: '["http://localhost:5173","http://127.0.0.1:5173"]',
        COMPLAINTS_TABLE_NAME: { Ref: Match.anyValue() }, INCIDENTS_TABLE_NAME: { Ref: Match.anyValue() },
        NEARBY_MAX_RADIUS_METERS: '200000', CLOUD_DISCOVERY_REGIONS_READY: 'false',
        AUDIT_EVENTS_TABLE_NAME: { Ref: Match.anyValue() }, EVIDENCE_BUCKET_NAME: { Ref: Match.anyValue() },
        COGNITO_CLIENT_ID: { Ref: Match.anyValue() },
      }) },
      LoggingConfig: { LogGroup: { Ref: Match.anyValue() } },
      Description: Match.stringLikeRegexp('SYNTHESIS ONLY'),
    })
    template.resourceCountIs('AWS::Lambda::Url', 0)
    template.resourceCountIs('AWS::Lambda::Version', 0)
  })

  it('keeps scoped logging and adds only required complaint/evidence permissions', () => {
    const { template } = foundation()
    template.hasResourceProperties('AWS::IAM::Role', {
      ManagedPolicyArns: Match.absent(),
      AssumeRolePolicyDocument: { Statement: [{ Action: 'sts:AssumeRole', Effect: 'Allow', Principal: { Service: 'lambda.amazonaws.com' } }], Version: '2012-10-17' },
    })
    template.hasResourceProperties('AWS::IAM::Policy', {
      PolicyDocument: { Statement: Match.arrayWith([{
        Action: ['logs:CreateLogStream', 'logs:PutLogEvents'], Effect: 'Allow',
        // Fn::GetAtt LogGroup.Arn already returns a stream wildcard; no suffix is added.
        Resource: { 'Fn::GetAtt': [Match.anyValue(), 'Arn'] },
      }]), Version: '2012-10-17' },
    })
    const policies = JSON.stringify(template.findResources('AWS::IAM::Policy'))
    expect(policies).toContain('dynamodb:UpdateItem')
    expect(policies).toContain('/index/ByCitizen')
    expect(policies).toContain('s3:DeleteObject')
    expect(policies).not.toMatch(/AdministratorAccess|dynamodb:\*|s3:\*|dynamodb:Scan|s3:ListBucket|dynamodb:DeleteItem/)
  })

  it('retains bounded seven-day log groups without observability helpers', () => {
    const { template } = foundation()
    template.resourceCountIs('AWS::Logs::LogGroup', 4)
    template.hasResource('AWS::Logs::LogGroup', {
      Properties: Match.objectLike({ LogGroupName: '/civiclens/demo/backend', RetentionInDays: 7 }),
      DeletionPolicy: 'Retain', UpdateReplacePolicy: 'Retain',
    })
    template.resourceCountIs('AWS::CloudWatch::Dashboard', 0)
    template.resourceCountIs('AWS::CloudWatch::Alarm', 0)
  })
})
