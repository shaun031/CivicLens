import { describe, expect, it } from 'vitest'
import { foundation } from './helpers.js'

describe('Phase9 work allocation preparation', () => {
  it('requires JWT scope for all work routes and retains the Phase14 deployment block', () => {
    const { template } = foundation()
    const routes = Object.values(template.toJSON().Resources).filter((r: any) => r.Type === 'AWS::ApiGatewayV2::Route') as any[]
    const work = routes.filter((r) => !r.Properties.RouteKey.includes('/analytics/') && !r.Properties.RouteKey.includes('/repair-attempts') && /departments|routing-rules|officers|assignments|assignment|assign-department|recommend-officer|assign-officer|reassign|unassign-officer|\/officer\/incidents/.test(r.Properties.RouteKey))
    expect(work).toHaveLength(29)
    for (const route of work) {
      expect(route.Properties.AuthorizationType).toBe('JWT')
      expect(route.Properties.AuthorizationScopes).toEqual(['civiclens/access'])
    }
    expect(template.toJSON().Rules.DeploymentBlockedUntilPhase14).toBeTruthy()
    template.resourceCountIs('AWS::DynamoDB::Table', 4)
    template.resourceCountIs('AWS::SQS::Queue', 4)
    template.resourceCountIs('AWS::SNS::Topic', 1)
    template.resourceCountIs('AWS::StepFunctions::StateMachine', 1)
  })
  it('defaults to manual approval and reuses the department index', () => {
    const { template } = foundation()
    template.hasResourceProperties('AWS::Lambda::Function', { Environment: { Variables: {
      ASSIGNMENT_MODE: 'MANUAL_APPROVAL', WORKLOAD_WEIGHTS: '[1,2,3,4]', MATCHING_WORKER_ENABLED: 'false',
    } } })
    expect(JSON.stringify(template.toJSON())).toContain('/index/ByDepartmentPriority')
  })
})
