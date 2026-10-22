import { describe, expect, it } from 'vitest'
import { foundation } from './helpers.js'
import { assertFoundationSafety, type FoundationTemplate } from '../lib/safety.js'

describe('Phase 5 public/private boundary', () => {
  it('exposes exactly three approved-issue endpoints without weakening private routes', () => {
    const { template } = foundation()
    for (const route of ['GET /api/citizen/issues/nearby', 'GET /api/citizen/issues/latest-location']) {
      template.hasResourceProperties('AWS::ApiGatewayV2::Route', {RouteKey:route,AuthorizationType:'JWT'})
    }
    const publicRoutes = ['GET /api/public/issues', 'GET /api/public/issues/nearby', 'GET /api/public/issues/{publicIssueId}']
    for (const route of publicRoutes) template.hasResourceProperties('AWS::ApiGatewayV2::Route', { RouteKey: route, AuthorizationType: 'NONE' })
    for (const route of ['PATCH /api/complaints/{complaintId}/publication-request', 'PATCH /api/admin/complaints/{complaintId}/publication']) template.hasResourceProperties('AWS::ApiGatewayV2::Route', { RouteKey: route, AuthorizationType: 'JWT', AuthorizationScopes: ['civiclens/access'] })
    const routes = Object.values(template.findResources('AWS::ApiGatewayV2::Route'))
    expect(routes.filter((route) => route.Properties.AuthorizationType === 'NONE')).toHaveLength(4)
  })
  it('rejects accidental anonymous administrator or private complaint access', () => {
    const document = foundation().template.toJSON()
    const route = Object.values(document.Resources as Record<string, { Type: string; Properties: { RouteKey?: string; AuthorizationType?: string } }>).find((resource) => resource.Properties?.RouteKey === 'PATCH /api/admin/complaints/{complaintId}/publication')!
    route.Properties.AuthorizationType = 'NONE'
    expect(() => assertFoundationSafety(document as FoundationTemplate)).toThrow('require JWT')
  })
  it('adds only exact geographic-index Query and append-only audit permissions', () => {
    const document = foundation().template.toJSON()
    const policies = Object.values(document.Resources as Record<string, { Type: string; Properties: object }>).filter((resource) => resource.Type === 'AWS::IAM::Policy')
    const serialized = JSON.stringify(policies)
    expect(serialized).toContain('/index/PublicGeography')
    expect(serialized).toContain('AuditEvents')
    expect(serialized).not.toMatch(/dynamodb:Scan|dynamodb:DeleteItem|ListBucket|dynamodb:\*/)
    assertFoundationSafety(document as FoundationTemplate)
  })
})
