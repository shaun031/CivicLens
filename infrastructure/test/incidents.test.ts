import { Match } from 'aws-cdk-lib/assertions'
import { describe, expect, it } from 'vitest'
import { assertFoundationSafety } from '../lib/safety.js'
import { foundation } from './helpers.js'

describe('Phase 7 incident foundation, offline only', () => {
  it('protects thirteen membership and ten priority routes with JWT, including owner-only summary', () => {
    const { template } = foundation()
    const routes = Object.values(template.findResources('AWS::ApiGatewayV2::Route')).filter(r => !String(r.Properties.RouteKey).includes('/analytics/') && !/repair-attempts|check-recurrence/.test(String(r.Properties.RouteKey)) && String(r.Properties.RouteKey).includes('incident'))
    expect(routes).toHaveLength(37)
    for (const route of routes) expect(route.Properties).toMatchObject({ AuthorizationType: 'JWT', AuthorizationScopes: ['civiclens/access'] })
    expect(routes.some(r => r.Properties.RouteKey === 'GET /api/complaints/{complaintId}/incident')).toBe(true)
  })
  it('keeps review-only configuration, scoped conditional transactions and the deployment guard', () => {
    const { template } = foundation()
    template.hasResourceProperties('AWS::Lambda::Function', { Environment: { Variables: Match.objectLike({ CLUSTERING_MODE: 'REVIEW_ONLY', CLUSTERING_MAX_MEMBERS: '30', CLUSTERING_REQUIRE_IMAGES: 'true', MATCHING_WORKER_ENABLED: 'false' }) } })
    const policies = JSON.stringify(template.findResources('AWS::IAM::Policy'))
    expect(policies).toContain('dynamodb:ConditionCheckItem')
    expect(policies).toContain('/index/ByCatalog')
    expect(policies).not.toMatch(/dynamodb:Scan|\/index\/\*/)
    expect(() => assertFoundationSafety(template.toJSON())).not.toThrow()
    const bad = JSON.parse(JSON.stringify(template.toJSON()))
    bad.Rules = {}
    expect(() => assertFoundationSafety(bad)).toThrow()
    template.resourceCountIs('AWS::DynamoDB::Table', 4)
    template.resourceCountIs('AWS::SQS::Queue', 4)
    template.resourceCountIs('AWS::StepFunctions::StateMachine', 1)
  })
})
