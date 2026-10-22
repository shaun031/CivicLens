import { Match } from 'aws-cdk-lib/assertions'
import { describe, expect, it } from 'vitest'
import { foundation } from './helpers.js'
import { assertFoundationSafety } from '../lib/safety.js'

describe('Phase 8 offline priority preparation', () => {
  it('protects all ten priority routes and permits audited override removal through DELETE', () => {
    const { template } = foundation()
    const routes = Object.values(template.findResources('AWS::ApiGatewayV2::Route')).filter(r => !String(r.Properties.RouteKey).includes('/analytics/') && /priorit|severity|public-impact|hazard-review/.test(String(r.Properties.RouteKey)))
    expect(routes).toHaveLength(10)
    for (const route of routes) expect(route.Properties).toMatchObject({ AuthorizationType: 'JWT', AuthorizationScopes: ['civiclens/access'] })
    expect(routes.some(r => r.Properties.RouteKey === 'DELETE /api/admin/incidents/{incidentId}/priority/override')).toBe(true)
  })
  it('reuses the existing priority GSI alongside Phase10 orchestration without broad permissions', () => {
    const { template } = foundation()
    template.resourceCountIs('AWS::DynamoDB::Table', 4)
    template.resourceCountIs('AWS::Events::Rule', 3)
    template.resourceCountIs('AWS::SQS::Queue', 4)
    template.resourceCountIs('AWS::SNS::Topic', 1)
    template.resourceCountIs('AWS::StepFunctions::StateMachine', 1)
    const policies = JSON.stringify(template.findResources('AWS::IAM::Policy'))
    expect(policies).toContain('/index/ByStatusPriority')
    expect(policies).toContain('dynamodb:ConditionCheckItem')
    expect(policies).not.toMatch(/dynamodb:Scan|dynamodb:DeleteItem|\/index\/\*/)
    template.hasResourceProperties('AWS::Lambda::Function', { Environment: { Variables: Match.objectLike({ PRIORITY_WEIGHTS: '[0.40,0.25,0.20,0.15]', PRIORITY_AGING_DAYS: '30', PRIORITY_REPORTER_SATURATION: '30', PRIORITY_REFRESH_SECONDS: '3600', MATCHING_WORKER_ENABLED: 'false' }) } })
    expect(() => assertFoundationSafety(template.toJSON())).not.toThrow()
  })
})
