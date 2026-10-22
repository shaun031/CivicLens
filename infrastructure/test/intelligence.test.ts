import { describe, expect, it } from 'vitest'
import { foundation } from './helpers.js'
import { INTELLIGENCE_EVENTS, INTELLIGENCE_ROUTES } from '../lib/intelligence-routes.js'
import { assertFoundationSafety } from '../lib/safety.js'

describe('Phase12 source-only civic intelligence preparation', () => {
  it('protects all 28 exact intelligence routes and preserves the deployment blocker', () => {
    const { template } = foundation()
    expect(INTELLIGENCE_ROUTES).toHaveLength(28)
    for (const [method,path] of INTELLIGENCE_ROUTES) template.hasResourceProperties('AWS::ApiGatewayV2::Route', { RouteKey:`${method} ${path}`, AuthorizationType:'JWT',AuthorizationScopes:['civiclens/access'] })
    expect(() => assertFoundationSafety(template.toJSON())).not.toThrow()
    expect(template.toJSON().Rules.DeploymentBlockedUntilPhase14).toBeTruthy()
  })
  it('routes versioned repair/recurrence events through the same queues and private evidence bucket', () => {
    const { template } = foundation()
    const rules=Object.values(template.findResources('AWS::Events::Rule'))
    const notification=rules.find(r=>r.Properties.EventPattern?.['detail-type']?.includes('RepairSubmitted'))!
    for(const event of INTELLIGENCE_EVENTS) expect(notification.Properties.EventPattern['detail-type']).toContain(event)
    template.resourceCountIs('AWS::DynamoDB::Table',4)
    template.resourceCountIs('AWS::S3::Bucket',1)
    template.resourceCountIs('AWS::Events::EventBus',1)
    expect(JSON.stringify(template.toJSON())).not.toMatch(/dynamodb:Scan|s3:PutObjectAcl/)
  })
})
