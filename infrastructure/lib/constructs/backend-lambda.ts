import { fileURLToPath } from 'node:url'
import { Duration, IgnoreMode } from 'aws-cdk-lib'
import * as iam from 'aws-cdk-lib/aws-iam'
import * as lambda from 'aws-cdk-lib/aws-lambda'
import type * as logs from 'aws-cdk-lib/aws-logs'
import { Construct } from 'constructs'
import type { CloudStage } from '../config/environment.js'
import type { Database } from './database.js'
import type { Storage } from './storage.js'
import type { Authentication } from './authentication.js'

interface BackendLambdaProps {
  readonly stage: CloudStage
  readonly frontendOrigins: readonly string[]
  readonly database: Database
  readonly storage: Storage
  readonly logGroup: logs.LogGroup
  readonly authentication: Authentication
  readonly entrypoint?: string
  readonly timeoutSeconds?: number
  readonly reservedConcurrency?: number
}

export class BackendLambda extends Construct {
  readonly handler: lambda.Function

  constructor(scope: Construct, id: string, props: BackendLambdaProps) {
    super(scope, id)
    const role = new iam.Role(this, 'ExecutionRole', {
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
      description: 'CivicLens API: scoped logs, complaints and private evidence only',
    })
    // CDK's logGroupArn already includes ':*' for dynamically created streams.
    role.addToPolicy(new iam.PolicyStatement({
      actions: ['logs:CreateLogStream', 'logs:PutLogEvents'],
      resources: [props.logGroup.logGroupArn],
    }))
    this.handler = new lambda.Function(this, 'Handler', {
      description: `CivicLens ${props.stage} API — SYNTHESIS ONLY: runtime dependencies missing; deployment blocked`,
      runtime: lambda.Runtime.PYTHON_3_13,
      architecture: lambda.Architecture.X86_64,
      handler: props.entrypoint ?? 'app.lambda_handler.handler',
      // Only Python source is staged. This is NOT a complete Lambda deployment package.
      code: lambda.Code.fromAsset(fileURLToPath(new URL('../../../backend', import.meta.url)), {
        ignoreMode: IgnoreMode.GLOB,
        exclude: ['data', 'data/**', '.venv', '.venv/**', 'tests', 'tests/**', '.env*', '.pytest_cache', '.pytest_cache/**', '.ruff_cache', '.ruff_cache/**', '.coverage', '.coverage.*', 'coverage', 'coverage/**', 'htmlcov', 'htmlcov/**', '**/__pycache__', '**/__pycache__/**', '**/*.pyc', 'pyproject.toml', 'requirements*.txt', 'build', 'build/**', 'dist', 'dist/**', '*.egg-info', '*.egg-info/**'],
      }),
      memorySize: props.entrypoint ? 512 : 256,
      timeout: Duration.seconds(props.timeoutSeconds ?? 15),
      reservedConcurrentExecutions: props.reservedConcurrency,
      logGroup: props.logGroup,
      role,
      tracing: lambda.Tracing.DISABLED,
      environment: {
        APP_NAME: 'CivicLens',
        APP_ENV: 'aws',
        AUTH_PROVIDER: 'cognito',
        COMPLAINT_PROVIDER: 'dynamodb',
        EVIDENCE_PROVIDER: 's3',
        NEARBY_MAX_RADIUS_METERS: '200000',
        CLOUD_DISCOVERY_REGIONS_READY: 'false',
        DISCOVERY_CANDIDATE_LIMIT: '2000',
        PUBLIC_QUERY_RATE_LIMIT: '120',
        CLOUD_OWNER_QUERY_LIMIT: '5000',
        MATCHING_WORKER_ENABLED: 'false',
        MATCHING_CANDIDATE_LIMIT: '90',
        MATCHING_JOB_SECONDS: '8',
        CLUSTERING_MODE: 'REVIEW_ONLY',
        CLUSTERING_MAX_MEMBERS: '30',
        CLUSTERING_REQUIRE_IMAGES: 'true',
        PRIORITY_WEIGHTS: '[0.40,0.25,0.20,0.15]',
        PRIORITY_BANDS: '[40,60,80]',
        PRIORITY_REPORTER_SATURATION: '30',
        PRIORITY_AGING_DAYS: '30',
        PRIORITY_REFRESH_SECONDS: '3600',
        ASSIGNMENT_MODE: 'MANUAL_APPROVAL',
        WORKLOAD_WEIGHTS: '[1,2,3,4]',
        ANALYTICS_SCOPE: 'municipality',
        ANALYTICS_TIMEZONE: 'UTC',
        ANALYTICS_MAX_INCIDENTS: '5000',
        ANALYTICS_MAX_COMPLAINTS: '10000',
        DEPLOYMENT_STAGE: props.stage,
        COGNITO_ISSUER: props.authentication.issuer,
        COGNITO_CLIENT_ID: props.authentication.client.userPoolClientId,
        COGNITO_DOMAIN: props.authentication.domain.baseUrl(),
        COGNITO_API_SCOPE: 'civiclens/access',
        DEBUG: 'false',
        LOG_LEVEL: 'INFO',
        CORS_ORIGINS: JSON.stringify(props.frontendOrigins),
        COMPLAINTS_TABLE_NAME: props.database.complaints.tableName,
        INCIDENTS_TABLE_NAME: props.database.incidents.tableName,
        AUDIT_EVENTS_TABLE_NAME: props.database.auditEvents.tableName,
        EVIDENCE_BUCKET_NAME: props.storage.evidence.bucketName,
      },
    })
    this.handler.node.addMetadata('civiclens:artifactReadiness', 'SOURCE_ONLY_NON_DEPLOYABLE')
  }
}
