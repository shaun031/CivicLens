import { Match } from 'aws-cdk-lib/assertions'
import { describe, expect, it } from 'vitest'
import { foundation } from './helpers.js'
import { assertFoundationSafety } from '../lib/safety.js'
import { WORKFLOW_ROUTES } from '../lib/workflow-routes.js'

describe('Phase10 event-driven foundation (offline)', () => {
  it('routes only supported source/version/types to encrypted queues with scoped target policies', () => {
    const { template } = foundation()
    template.resourceCountIs('AWS::Events::EventBus', 1)
    const rules = Object.values(template.findResources('AWS::Events::Rule')).filter(r => r.Properties.EventPattern)
    expect(rules).toHaveLength(2)
    for (const rule of rules) {
      expect(rule.Properties.EventPattern.source).toEqual(['civiclens.domain'])
      expect(rule.Properties.EventPattern.detail.eventVersion).toEqual([1])
      expect(rule.Properties.Targets).toHaveLength(1)
    }
    template.resourceCountIs('AWS::SQS::Queue', 4)
    template.allResourcesProperties('AWS::SQS::Queue', { SqsManagedSseEnabled: true })
    const queues = Object.values(template.findResources('AWS::SQS::Queue')).filter(r => r.Properties.RedrivePolicy)
    expect(queues).toHaveLength(2)
    for (const q of queues) expect(q.Properties).toMatchObject({ VisibilityTimeout: 600, MessageRetentionPeriod: 345600, RedrivePolicy: { maxReceiveCount: 5 } })
    const policies = Object.values(template.findResources('AWS::SQS::QueuePolicy'))
    for (const policy of policies) for (const statement of policy.Properties.PolicyDocument.Statement) {
      expect(statement.Principal).toEqual({ Service: 'events.amazonaws.com' })
      expect(statement.Condition.ArnEquals['aws:SourceArn']).toBeTruthy()
      expect(JSON.stringify(statement.Resource)).not.toBe('"*"')
    }
  })
  it('uses bounded partial-failure SQS batches without provisioned polling, VPCs or concurrency', () => {
    const { template } = foundation()
    template.allResourcesProperties('AWS::Lambda::EventSourceMapping', { BatchSize: 1, FunctionResponseTypes: ['ReportBatchItemFailures'], ScalingConfig: { MaximumConcurrency: 2 }, ProvisionedPollerConfig: Match.absent() })
    for (const fn of Object.values(template.findResources('AWS::Lambda::Function'))) {
      expect(fn.Properties.Timeout).toBeLessThanOrEqual(90)
      expect(fn.Properties.VpcConfig).toBeUndefined()
    }
    template.resourceCountIs('AWS::Lambda::Version', 0)
    template.allResourcesProperties('AWS::Logs::LogGroup', { RetentionInDays: 7 })
  })
  it('defines a terminating Standard workflow with bounded retries/catches and a disabled hourly schedule', () => {
    const { template } = foundation()
    template.hasResourceProperties('AWS::StepFunctions::StateMachine', { StateMachineType: 'STANDARD', TimeoutSeconds: Match.absent() })
    const machine = JSON.stringify(template.findResources('AWS::StepFunctions::StateMachine'))
    for (const state of ['ValidateComplaint', 'RunDuplicateDetection', 'EvaluateClustering', 'RecalculatePriority', 'RouteDepartment', 'EvaluateNotifications', 'CompleteWorkflow', 'RecordFailure', 'ReviewRequired', 'EligibleComplaint', 'Retry', 'Catch', 'Succeed', 'Fail']) expect(machine).toContain(state)
    expect(machine).toContain('TransientWorkflowError')
    expect(machine).not.toContain('waitForTaskToken')
    template.hasResourceProperties('AWS::Events::Rule', { ScheduleExpression: 'rate(1 hour)', State: 'DISABLED' })
    template.resourceCountIs('AWS::SNS::Topic', 1)
    template.resourceCountIs('AWS::SNS::Subscription', 0)
    const { stack } = foundation()
    expect(Object.keys(stack.workflows.metrics)).toContain('executionFailures')
    expect(stack.workflows.metrics.processingDeadLetters!.namespace).toBe('AWS/SQS')
    expect(stack.workflows.metrics.scheduledCheckErrors!.namespace).toBe('AWS/Lambda')
  })
  it('protects all15 control routes, scopes IAM to named resources and retains the deployment blocker', () => {
    const { template } = foundation()
    for (const [verb, path] of WORKFLOW_ROUTES) template.hasResourceProperties('AWS::ApiGatewayV2::Route', { RouteKey: `${verb} ${path}`, AuthorizationType: 'JWT', AuthorizationScopes: ['civiclens/access'] })
    expect(() => assertFoundationSafety(template.toJSON())).not.toThrow()
    const policies = JSON.stringify(template.findResources('AWS::IAM::Policy'))
    expect(policies).not.toMatch(/AdministratorAccess|dynamodb:Scan|dynamodb:DeleteItem|sns:\*|sqs:\*|states:\*|"Resource":"\*"/)
    expect(policies).toContain('events:PutEvents'); expect(policies).toContain('states:StartExecution')
    expect(policies).toContain('/index/ByQueue')
  })
})
