import { Match } from 'aws-cdk-lib/assertions'
import { describe, expect, it } from 'vitest'
import { assertFoundationSafety } from '../lib/safety.js'
import { foundation } from './helpers.js'

describe('Phase 6 matching preparation', () => {
  it('protects all seven matching routes with JWT and the application scope', () => {
    const { template } = foundation()
    const routes = Object.values(template.findResources('AWS::ApiGatewayV2::Route')).filter((value) => String(value.Properties.RouteKey).includes('duplicate'))
    expect(routes).toHaveLength(7)
    for (const route of routes) expect(route.Properties).toMatchObject({ AuthorizationType: 'JWT', AuthorizationScopes: ['civiclens/access'] })
    template.hasResourceProperties('AWS::Lambda::Function', { Environment: { Variables: Match.objectLike({ MATCHING_WORKER_ENABLED: 'false', MATCHING_CANDIDATE_LIMIT: '90' }) } })
  })
  it('keeps internal and public indexes separate alongside the Phase10 orchestration sidecar', () => {
    const { template } = foundation()
    template.resourceCountIs('AWS::DynamoDB::Table', 4)
    template.resourceCountIs('AWS::SQS::Queue', 4)
    template.resourceCountIs('AWS::Events::Rule', 3)
    const tables = Object.values(template.findResources('AWS::DynamoDB::Table'))
    const complaint = tables.find((value) => JSON.stringify(value.Properties.KeySchema).includes('complaintId'))
    expect(complaint?.Properties.GlobalSecondaryIndexes.map((value: { IndexName: string }) => value.IndexName)).toEqual(['ByCitizen', 'ByIncident', 'PublicGeography', 'InternalGeography', 'MatchingWork'])
    expect(() => assertFoundationSafety(template.toJSON())).not.toThrow()
  })
  it('does not permit Scan, broad indexes, private-public index aliases or bypassing deployment guard', () => {
    const { template } = foundation()
    const policies = JSON.stringify(template.findResources('AWS::IAM::Policy'))
    expect(policies).not.toContain('dynamodb:Scan')
    expect(policies).toContain('/index/InternalGeography')
    expect(policies).toContain('/index/MatchingWork')
    expect(policies).not.toContain('/index/*')
    const bad = JSON.parse(JSON.stringify(template.toJSON()))
    const policy = Object.values(bad.Resources).find((value: unknown) => (value as { Type: string }).Type === 'AWS::IAM::Policy') as { Properties: { PolicyDocument: { Statement: { Action: string }[] } } }
    policy.Properties.PolicyDocument.Statement.push({ Action: 'dynamodb:Scan' })
    expect(() => assertFoundationSafety(bad)).toThrow()
  })
})
