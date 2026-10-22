import { CfnOutput, CfnRule, Fn, Stack, Tags, type StackProps } from 'aws-cdk-lib'
import type { Construct } from 'constructs'
import type { CloudStage, EnvironmentConfig } from '../config/environment.js'
import { ApiGateway } from '../constructs/api-gateway.js'
import { BackendLambda } from '../constructs/backend-lambda.js'
import { Database } from '../constructs/database.js'
import { Monitoring } from '../constructs/monitoring.js'
import { Storage } from '../constructs/storage.js'
import { ApplicationPermissions } from '../permissions.js'
import { Authentication } from '../constructs/authentication.js'
import { Workflows } from '../constructs/workflows.js'

export interface CivicLensStackProps extends StackProps {
  readonly config: EnvironmentConfig & { readonly stage: CloudStage }
}

export class CivicLensStack extends Stack {
  readonly database: Database
  readonly storage: Storage
  readonly monitoring: Monitoring
  readonly backend: BackendLambda
  readonly gateway: ApiGateway
  readonly permissions: ApplicationPermissions
  readonly authentication: Authentication
  readonly workflows: Workflows

  constructor(scope: Construct, id: string, props: CivicLensStackProps) {
    super(scope, id, props)
    const { config } = props
    Tags.of(this).add('Project', 'CivicLens')
    Tags.of(this).add('Stage', config.stage)
    this.database = new Database(this, 'Database', config.stage === 'production')
    this.storage = new Storage(this, 'Storage', config.frontendOrigins)
    this.monitoring = new Monitoring(this, 'Monitoring', config.stage)
    this.authentication = new Authentication(this, 'Authentication', config)
    this.backend = new BackendLambda(this, 'Backend', {
      stage: config.stage,
      frontendOrigins: config.frontendOrigins,
      database: this.database,
      storage: this.storage,
      logGroup: this.monitoring.backendLogs,
      authentication: this.authentication,
    })
    this.gateway = new ApiGateway(this, 'Gateway', this.backend.handler, config.frontendOrigins, this.authentication)
    this.permissions = new ApplicationPermissions(this.database, this.storage)
    this.permissions.grantComplaintBackend(this.backend.handler)
    this.workflows = new Workflows(this, 'Workflows', config)

    // Intentionally unsatisfiable until reviewed and replaced during Phase 14.
    new CfnRule(this, 'DeploymentBlockedUntilPhase14', {
      assertions: [{
        assert: Fn.conditionEquals('PHASE_1_SYNTHESIS_ONLY', 'PHASE_14_APPROVED_READY_ARTIFACT'),
        assertDescription: 'Deployment is blocked: Phase 14 approval and a verified Linux Lambda artifact are required.',
      }],
    })
    this.templateOptions.metadata = {
      CivicLens: { phase: 12, deployed: false, artifactReadiness: 'SOURCE_ONLY_NON_DEPLOYABLE', callbackUrlsRequirePhase14Validation: true },
    }
    const outputs: Record<string, string> = {
      ApiEndpointUrl: this.gateway.api.apiEndpoint,
      LambdaFunctionName: this.backend.handler.functionName,
      ComplaintsTableName: this.database.complaints.tableName,
      IncidentsTableName: this.database.incidents.tableName,
      AuditEventsTableName: this.database.auditEvents.tableName,
      EvidenceBucketName: this.storage.evidence.bucketName,
      DeploymentStage: config.stage,
      CognitoUserPoolId: this.authentication.userPool.userPoolId,
      CognitoClientId: this.authentication.client.userPoolClientId,
      CognitoIssuer: this.authentication.issuer,
      CognitoDomainUrl: this.authentication.domain.baseUrl(),
      FrontendCallbackUrls: JSON.stringify(config.callbackUrls),
      FrontendLogoutUrls: JSON.stringify(config.logoutUrls),
    }
    for (const [name, value] of Object.entries(outputs)) {
      new CfnOutput(this, name, { value, description: 'Future identifier; no resource exists until an approved Phase 14 deployment.' })
    }
  }
}
