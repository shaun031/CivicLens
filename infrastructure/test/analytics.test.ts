import { Match } from 'aws-cdk-lib/assertions'
import { describe, expect, it } from 'vitest'
import { foundation } from './helpers.js'
import { ANALYTICS_ROUTES } from '../lib/analytics-routes.js'
import { assertFoundationSafety } from '../lib/safety.js'

describe('Phase11 bounded municipal analytics preparation', () => {
  it('protects every exact analytics and export route with existing Cognito scope', () => {
    const { template } = foundation()
    expect(ANALYTICS_ROUTES).toHaveLength(13)
    for (const [method, path] of ANALYTICS_ROUTES) template.hasResourceProperties('AWS::ApiGatewayV2::Route', { RouteKey: `${method} ${path}`, AuthorizationType: 'JWT', AuthorizationScopes: ['civiclens/access'] })
    expect(() => assertFoundationSafety(template.toJSON())).not.toThrow()
  })
  it('reuses the operations table and worker infrastructure without analytics clusters', () => {
    const { template } = foundation()
    template.resourceCountIs('AWS::DynamoDB::Table', 4)
    template.resourceCountIs('AWS::Lambda::Function', 4)
    template.allResourcesProperties('AWS::Lambda::Function', { Environment: { Variables: Match.objectLike({ ANALYTICS_TIMEZONE: 'UTC', ANALYTICS_SCOPE: 'municipality', ANALYTICS_MAX_INCIDENTS: '5000' }) } })
    const types = Object.values(template.toJSON().Resources).map((r: unknown) => (r as { Type: string }).Type)
    expect(types.some((t: string) => /OpenSearch|Redshift|Kinesis|NatGateway|EC2::Instance/.test(t))).toBe(false)
    expect(JSON.stringify(template.toJSON())).not.toContain('dynamodb:Scan')
    expect(template.toJSON().Rules.DeploymentBlockedUntilPhase14).toBeTruthy()
  })
})
