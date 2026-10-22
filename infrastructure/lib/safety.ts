import { WORKFLOW_ROUTES } from './workflow-routes.js'
import { ANALYTICS_ROUTES } from './analytics-routes.js'
import { INTELLIGENCE_ROUTES } from './intelligence-routes.js'

export interface TemplateResource {
  readonly Type: string
  readonly Properties?: Record<string, unknown>
  readonly DeletionPolicy?: string
  readonly UpdateReplacePolicy?: string
}

export interface FoundationTemplate {
  readonly Resources?: Record<string, TemplateResource>
  readonly Rules?: Record<string, unknown>
  readonly Metadata?: Record<string, unknown>
}

const expectedResourceCounts: Readonly<Record<string, number>> = Object.freeze({
  'AWS::DynamoDB::Table': 4,
  'AWS::S3::Bucket': 1,
  'AWS::S3::BucketPolicy': 1,
  'AWS::Lambda::Function': 4,
  'AWS::Lambda::Permission': 134,
  'AWS::IAM::Role': 5,
  'AWS::IAM::Policy': 5,
  'AWS::Logs::LogGroup': 4,
  'AWS::ApiGatewayV2::Api': 1,
  'AWS::ApiGatewayV2::Integration': 133,
  'AWS::ApiGatewayV2::Route': 133,
  'AWS::ApiGatewayV2::Stage': 1,
  'AWS::ApiGatewayV2::Authorizer': 1,
  'AWS::Cognito::UserPool': 1,
  'AWS::Cognito::UserPoolClient': 1,
  'AWS::Cognito::UserPoolDomain': 1,
  'AWS::Cognito::UserPoolResourceServer': 1,
  'AWS::Cognito::UserPoolGroup': 3,
  'AWS::Events::EventBus': 1,
  'AWS::Events::Rule': 3,
  'AWS::SQS::Queue': 4,
  'AWS::SQS::QueuePolicy': 4,
  'AWS::SNS::Topic': 1,
  'AWS::StepFunctions::StateMachine': 1,
  'AWS::Lambda::EventSourceMapping': 2,
})

/** Offline checks against actual synthesized templates, without AWS APIs. */
export function assertFoundationSafety(template: FoundationTemplate): void {
  const resources = Object.values(template.Resources ?? {})
  const entries = Object.entries(template.Resources ?? {})
  const arn = (id: string) => ({ 'Fn::GetAtt': [id, 'Arn'] })
  const ids = (type: string) => entries.filter(([, r]) => r.Type === type).map(([id]) => id)
  const logArns = ids('AWS::Logs::LogGroup').map(id => JSON.stringify(arn(id)))
  const queueArns = ids('AWS::SQS::Queue').filter(id => !id.includes('Dead')).map(id => JSON.stringify(arn(id)))
  const operationsId = entries.find(([, r]) => r.Type === 'AWS::DynamoDB::Table' && JSON.stringify(r.Properties?.KeySchema).includes('"pk"'))?.[0]
  const operationsArn = JSON.stringify(arn(operationsId!))
  const operationsIndexArn = JSON.stringify({ 'Fn::Join': ['', [arn(operationsId!), '/index/ByQueue']] })
  const busArn = JSON.stringify(arn(ids('AWS::Events::EventBus')[0]!))
  const topicArn = JSON.stringify({ Ref: ids('AWS::SNS::Topic')[0] })
  const machineArn = JSON.stringify({ Ref: ids('AWS::StepFunctions::StateMachine')[0] })
  const stepId = entries.find(([, r]) => r.Type === 'AWS::Lambda::Function' && r.Properties?.Handler === 'app.workflow_handlers.step_handler')?.[0]
  const stepArns = JSON.stringify([arn(stepId!), { 'Fn::Join': ['', [arn(stepId!), ':*']] }])
  const logGroupId = Object.entries(template.Resources ?? {}).find(([, resource]) => resource.Type === 'AWS::Logs::LogGroup')?.[0]
  const complaintTableId = Object.entries(template.Resources ?? {}).find(([, resource]) => resource.Type === 'AWS::DynamoDB::Table' && JSON.stringify(resource.Properties?.KeySchema).includes('complaintId'))?.[0]
  const evidenceBucketId = Object.entries(template.Resources ?? {}).find(([, resource]) => resource.Type === 'AWS::S3::Bucket')?.[0]
  const auditTableId = Object.entries(template.Resources ?? {}).find(([, resource]) => resource.Type === 'AWS::DynamoDB::Table' && JSON.stringify(resource.Properties?.KeySchema).includes('timestampEventId'))?.[0]
  const incidentTableId = Object.entries(template.Resources ?? {}).find(([, resource]) => resource.Type === 'AWS::DynamoDB::Table' && JSON.stringify(resource.Properties?.KeySchema).includes('incidentId'))?.[0]
  const counts: Record<string, number> = {}
  for (const resource of resources) counts[resource.Type] = (counts[resource.Type] ?? 0) + 1
  for (const [type, count] of Object.entries(expectedResourceCounts)) {
    if (counts[type] !== count) throw new Error(`Expected ${count} ${type} resources, found ${counts[type] ?? 0}`)
  }
  for (const type of Object.keys(counts)) {
    if (!(type in expectedResourceCounts)) throw new Error(`Unexpected or prohibited resource: ${type}`)
  }
  for (const resource of resources) {
    const properties = resource.Properties ?? {}
    if (resource.Type === 'AWS::IAM::Role' && (properties.ManagedPolicyArns !== undefined || properties.Policies !== undefined)) {
      throw new Error('The health execution role must use only the explicitly checked logging policy')
    }
    if (resource.Type === 'AWS::IAM::Policy') {
      const policy = properties.PolicyDocument as { Statement: { Effect: string; Action: string | string[]; Resource: unknown }[] }
      for (const statement of policy.Statement) {
        const actions = Array.isArray(statement.Action) ? statement.Action : [statement.Action]
        const resourceJson = JSON.stringify(statement.Resource)
        const logArn = JSON.stringify({ 'Fn::GetAtt': [logGroupId, 'Arn'] })
        const tableArn = JSON.stringify({ 'Fn::GetAtt': [complaintTableId, 'Arn'] })
        const indexArn = JSON.stringify({ 'Fn::Join': ['', [{ 'Fn::GetAtt': [complaintTableId, 'Arn'] }, '/index/ByCitizen']] })
        const publicIndexArn = JSON.stringify({ 'Fn::Join': ['', [{ 'Fn::GetAtt': [complaintTableId, 'Arn'] }, '/index/PublicGeography']] })
        const internalIndexArn = JSON.stringify({ 'Fn::Join': ['', [{ 'Fn::GetAtt': [complaintTableId, 'Arn'] }, '/index/InternalGeography']] })
        const matchingIndexArn = JSON.stringify({ 'Fn::Join': ['', [{ 'Fn::GetAtt': [complaintTableId, 'Arn'] }, '/index/MatchingWork']] })
        const auditArn = JSON.stringify({ 'Fn::GetAtt': [auditTableId, 'Arn'] })
        const incidentArn = JSON.stringify({ 'Fn::GetAtt': [incidentTableId, 'Arn'] })
        const incidentCatalogArn = JSON.stringify({ 'Fn::Join': ['', [{ 'Fn::GetAtt': [incidentTableId, 'Arn'] }, '/index/ByCatalog']] })
        const priorityIndexArn = JSON.stringify({ 'Fn::Join': ['', [{ 'Fn::GetAtt': [incidentTableId, 'Arn'] }, '/index/ByStatusPriority']] })
        const departmentIndexArn = JSON.stringify({ 'Fn::Join': ['', [{ 'Fn::GetAtt': [incidentTableId, 'Arn'] }, '/index/ByDepartmentPriority']] })
        const evidenceArn = JSON.stringify({ 'Fn::Join': ['', [{ 'Fn::GetAtt': [evidenceBucketId, 'Arn'] }, '/complaints/*']] })
        const allowed = resourceJson === logArn || logArns.includes(resourceJson) ? ['logs:CreateLogStream', 'logs:PutLogEvents']
          : resourceJson === operationsArn ? ['dynamodb:GetItem', 'dynamodb:PutItem', 'dynamodb:UpdateItem', 'dynamodb:ConditionCheckItem']
          : resourceJson === operationsIndexArn ? ['dynamodb:Query']
          : resourceJson === busArn ? ['events:PutEvents']
          : resourceJson === topicArn ? ['sns:Publish']
          : resourceJson === machineArn ? ['states:StartExecution']
          : resourceJson === stepArns ? ['lambda:InvokeFunction']
          : queueArns.includes(resourceJson) ? ['sqs:ReceiveMessage', 'sqs:ChangeMessageVisibility', 'sqs:GetQueueUrl', 'sqs:DeleteMessage', 'sqs:GetQueueAttributes']
          : resourceJson === tableArn ? ['dynamodb:GetItem', 'dynamodb:BatchGetItem', 'dynamodb:PutItem', 'dynamodb:UpdateItem', 'dynamodb:ConditionCheckItem']
          : resourceJson === incidentArn ? ['dynamodb:GetItem', 'dynamodb:PutItem', 'dynamodb:UpdateItem', 'dynamodb:ConditionCheckItem']
          : resourceJson === incidentCatalogArn || resourceJson === priorityIndexArn || resourceJson === departmentIndexArn ? ['dynamodb:Query']
          : resourceJson === indexArn ? ['dynamodb:Query']
          : resourceJson === publicIndexArn ? ['dynamodb:Query']
          : resourceJson === internalIndexArn || resourceJson === matchingIndexArn ? ['dynamodb:Query']
          : resourceJson === auditArn ? ['dynamodb:PutItem', 'dynamodb:Query']
          : resourceJson === evidenceArn ? ['s3:GetObject', 's3:PutObject', 's3:DeleteObject'] : []
        if (statement.Effect !== 'Allow' || !actions.length || actions.some(action => !allowed.includes(action))) throw new Error('Unexpected or overbroad complaint backend IAM permission')
      }
    }
    if (resource.Type === 'AWS::Lambda::Function' && (properties.VpcConfig !== undefined || properties.Layers !== undefined)) {
      throw new Error('The Phase 1 function must not use a VPC or layers')
    }
    if (resource.Type === 'AWS::ApiGatewayV2::Route') {
      const publicRoutes = ['GET /api/public/issues', 'GET /api/public/issues/nearby', 'GET /api/public/issues/{publicIssueId}']
      const allowed = ['GET /api/health', 'GET /api/auth/me', 'PATCH /api/profile', 'GET /api/portal/citizen', 'GET /api/portal/officer', 'GET /api/portal/admin', 'POST /api/complaints', 'GET /api/complaints', 'GET /api/complaints/summary', 'GET /api/complaints/{complaintId}', 'GET /api/complaints/{complaintId}/images/{imageId}', 'PATCH /api/complaints/{complaintId}/publication-request', 'PATCH /api/admin/complaints/{complaintId}/publication',
        'GET /api/admin/duplicate-candidates', 'GET /api/admin/duplicate-candidates/{candidateId}',
        'GET /api/admin/complaints/{complaintId}/duplicate-candidates',
        'POST /api/admin/duplicate-candidates/{candidateId}/dismiss',
        'POST /api/admin/duplicate-candidates/{candidateId}/reviewed',
        'POST /api/admin/complaints/{complaintId}/duplicate-check',
        'GET /api/admin/duplicate-candidates/{candidateId}/complaints/{complaintId}/images/{imageId}',
        'GET /api/admin/incidents', 'GET /api/admin/incidents/summary',
        'GET /api/admin/incidents/{incidentId}', 'GET /api/admin/incidents/{incidentId}/complaints',
        'GET /api/admin/incidents/{incidentId}/history', 'GET /api/admin/incidents/{incidentId}/recommendations',
        'POST /api/admin/incidents/merge', 'POST /api/admin/incidents/{incidentId}/link-complaint',
        'POST /api/admin/incidents/{incidentId}/unlink-complaint', 'POST /api/admin/incidents/{incidentId}/split',
        'POST /api/admin/incidents/{incidentId}/recheck',
        'GET /api/admin/incidents/{incidentId}/complaints/{complaintId}/images/{imageId}',
        'GET /api/admin/incidents/priorities', 'GET /api/admin/incidents/priorities/summary',
        'GET /api/admin/incidents/{incidentId}/priority', 'GET /api/admin/incidents/{incidentId}/priority/history',
        'POST /api/admin/incidents/{incidentId}/priority/recalculate',
        'PATCH /api/admin/incidents/{incidentId}/severity', 'PATCH /api/admin/incidents/{incidentId}/public-impact',
        'PATCH /api/admin/incidents/{incidentId}/hazard-review',
        'POST /api/admin/incidents/{incidentId}/priority/override', 'DELETE /api/admin/incidents/{incidentId}/priority/override',
        'GET /api/admin/departments/summary', 'POST /api/admin/departments/seed',
        'GET /api/admin/departments', 'POST /api/admin/departments',
        'GET /api/admin/departments/{departmentId}', 'PATCH /api/admin/departments/{departmentId}',
        'GET /api/admin/departments/{departmentId}/officers', 'POST /api/admin/departments/{departmentId}/officers',
        'DELETE /api/admin/departments/{departmentId}/officers/{officerId}',
        'GET /api/admin/departments/{departmentId}/incidents', 'GET /api/admin/departments/{departmentId}/history',
        'GET /api/admin/routing-rules', 'POST /api/admin/routing-rules', 'GET /api/admin/officers',
        'GET /api/admin/assignments', 'GET /api/admin/assignments/unassigned',
        'GET /api/admin/incidents/{incidentId}/assignment', 'GET /api/admin/incidents/{incidentId}/assignment-history',
        'POST /api/admin/incidents/{incidentId}/assign-department', 'POST /api/admin/incidents/{incidentId}/recommend-officer',
        'POST /api/admin/incidents/{incidentId}/assign-officer', 'POST /api/admin/incidents/{incidentId}/reassign',
        'POST /api/admin/incidents/{incidentId}/unassign-officer',
        'GET /api/officer/incidents', 'GET /api/officer/incidents/{incidentId}',
        'GET /api/officer/incidents/{incidentId}/history', 'POST /api/officer/incidents/{incidentId}/start',
        'POST /api/officer/incidents/{incidentId}/progress',
        'GET /api/officer/incidents/{incidentId}/complaints/{complaintId}/images/{imageId}',
        'GET /api/complaints/{complaintId}/incident', ...[...WORKFLOW_ROUTES,...ANALYTICS_ROUTES,...INTELLIGENCE_ROUTES].map(([method, path]) => `${method} ${path}`), ...publicRoutes]
      allowed.push('GET /api/citizen/issues/nearby', 'GET /api/citizen/issues/latest-location')
      if (!allowed.includes(properties.RouteKey as string)) throw new Error('Unexpected public or application route')
      if (properties.RouteKey === 'GET /api/health' || publicRoutes.includes(properties.RouteKey as string)) {
        if (properties.AuthorizationType !== 'NONE') throw new Error('Health must remain public')
      } else if (properties.AuthorizationType !== 'JWT' || !properties.AuthorizerId || JSON.stringify(properties.AuthorizationScopes) !== '["civiclens/access"]') {
        throw new Error('Sensitive identity and portal routes require JWT authorization and the API scope')
      }
    }
  }
  const rule = template.Rules?.DeploymentBlockedUntilPhase14 as { Assertions?: { Assert: unknown }[]; RuleCondition?: unknown } | undefined
  const expectedAssertion = { 'Fn::Equals': ['PHASE_1_SYNTHESIS_ONLY', 'PHASE_14_APPROVED_READY_ARTIFACT'] }
  if (rule?.RuleCondition !== undefined || JSON.stringify(rule?.Assertions?.[0]?.Assert) !== JSON.stringify(expectedAssertion)) {
    throw new Error('Missing unconditional Phase 14 deployment blocker')
  }
}

/** Remains blocked until Phase 14 review; no context/environment bypass exists. */
export function assertDeploymentReadiness(): never {
  throw new Error('NOT DEPLOYABLE: The Lambda asset is source-only. Phase 14 approval, real OAuth URLs, trusted citizen provisioning, pinned Linux dependencies, artifact integrity checks, and runtime verification are required. See docs/INFRASTRUCTURE.md.')
}
