import { Duration } from 'aws-cdk-lib'
import * as apigateway from 'aws-cdk-lib/aws-apigatewayv2'
import { HttpLambdaIntegration } from 'aws-cdk-lib/aws-apigatewayv2-integrations'
import { HttpJwtAuthorizer } from 'aws-cdk-lib/aws-apigatewayv2-authorizers'
import { API_SCOPE, type Authentication } from './authentication.js'
import type * as lambda from 'aws-cdk-lib/aws-lambda'
import { Construct } from 'constructs'
import { WORKFLOW_ROUTES } from '../workflow-routes.js'
import { ANALYTICS_ROUTES } from '../analytics-routes.js'
import { INTELLIGENCE_ROUTES } from '../intelligence-routes.js'

export class ApiGateway extends Construct {
  readonly api: apigateway.HttpApi

  constructor(scope: Construct, id: string, handler: lambda.IFunction, frontendOrigins: readonly string[], authentication: Authentication) {
    super(scope, id)
    this.api = new apigateway.HttpApi(this, 'HttpApi', {
      description: 'CivicLens public health and JWT-protected identity, complaints and evidence',
      corsPreflight: frontendOrigins.length ? {
        allowOrigins: [...frontendOrigins],
        allowMethods: [apigateway.CorsHttpMethod.GET, apigateway.CorsHttpMethod.PATCH, apigateway.CorsHttpMethod.POST, apigateway.CorsHttpMethod.DELETE, apigateway.CorsHttpMethod.PUT],
        allowHeaders: ['content-type', 'authorization', 'idempotency-key'],
        allowCredentials: false,
        maxAge: Duration.minutes(10),
      } : undefined,
    })
    this.api.addRoutes({
      path: '/api/health',
      methods: [apigateway.HttpMethod.GET],
      integration: new HttpLambdaIntegration('HealthIntegration', handler, {
        payloadFormatVersion: apigateway.PayloadFormatVersion.VERSION_2_0,
      }),
    })
    for (const path of ['/api/public/issues', '/api/public/issues/nearby', '/api/public/issues/{publicIssueId}']) {
      this.api.addRoutes({ path, methods: [apigateway.HttpMethod.GET], integration: new HttpLambdaIntegration(`GET${path}`, handler, { payloadFormatVersion: apigateway.PayloadFormatVersion.VERSION_2_0 }) })
    }
    const authorizer = new HttpJwtAuthorizer('CognitoJwtAuthorizer', authentication.issuer, {
      jwtAudience: [authentication.client.userPoolClientId],
    })
    for (const [method, path] of [
      [apigateway.HttpMethod.GET, '/api/auth/me'],
      [apigateway.HttpMethod.PATCH, '/api/profile'],
      [apigateway.HttpMethod.GET, '/api/portal/citizen'],
      [apigateway.HttpMethod.GET, '/api/portal/officer'],
      [apigateway.HttpMethod.GET, '/api/portal/admin'],
      [apigateway.HttpMethod.POST, '/api/complaints'],
      [apigateway.HttpMethod.GET, '/api/complaints'],
      [apigateway.HttpMethod.GET, '/api/complaints/summary'],
      [apigateway.HttpMethod.GET, '/api/citizen/issues/nearby'],
      [apigateway.HttpMethod.GET, '/api/citizen/issues/latest-location'],
      [apigateway.HttpMethod.GET, '/api/complaints/{complaintId}'],
      [apigateway.HttpMethod.GET, '/api/complaints/{complaintId}/images/{imageId}'],
      [apigateway.HttpMethod.PATCH, '/api/complaints/{complaintId}/publication-request'],
      [apigateway.HttpMethod.PATCH, '/api/admin/complaints/{complaintId}/publication'],
      [apigateway.HttpMethod.GET, '/api/admin/duplicate-candidates'],
      [apigateway.HttpMethod.GET, '/api/admin/duplicate-candidates/{candidateId}'],
      [apigateway.HttpMethod.GET, '/api/admin/complaints/{complaintId}/duplicate-candidates'],
      [apigateway.HttpMethod.POST, '/api/admin/duplicate-candidates/{candidateId}/dismiss'],
      [apigateway.HttpMethod.POST, '/api/admin/duplicate-candidates/{candidateId}/reviewed'],
      [apigateway.HttpMethod.POST, '/api/admin/complaints/{complaintId}/duplicate-check'],
      [apigateway.HttpMethod.GET, '/api/admin/duplicate-candidates/{candidateId}/complaints/{complaintId}/images/{imageId}'],
      [apigateway.HttpMethod.GET, '/api/admin/incidents'],
      [apigateway.HttpMethod.GET, '/api/admin/incidents/summary'],
      [apigateway.HttpMethod.GET, '/api/admin/incidents/{incidentId}'],
      [apigateway.HttpMethod.GET, '/api/admin/incidents/{incidentId}/complaints'],
      [apigateway.HttpMethod.GET, '/api/admin/incidents/{incidentId}/history'],
      [apigateway.HttpMethod.GET, '/api/admin/incidents/{incidentId}/recommendations'],
      [apigateway.HttpMethod.POST, '/api/admin/incidents/merge'],
      [apigateway.HttpMethod.POST, '/api/admin/incidents/{incidentId}/link-complaint'],
      [apigateway.HttpMethod.POST, '/api/admin/incidents/{incidentId}/unlink-complaint'],
      [apigateway.HttpMethod.POST, '/api/admin/incidents/{incidentId}/split'],
      [apigateway.HttpMethod.POST, '/api/admin/incidents/{incidentId}/recheck'],
      [apigateway.HttpMethod.GET, '/api/admin/incidents/{incidentId}/complaints/{complaintId}/images/{imageId}'],
      [apigateway.HttpMethod.GET, '/api/complaints/{complaintId}/incident'],
      [apigateway.HttpMethod.GET, '/api/admin/incidents/priorities'],
      [apigateway.HttpMethod.GET, '/api/admin/incidents/priorities/summary'],
      [apigateway.HttpMethod.GET, '/api/admin/incidents/{incidentId}/priority'],
      [apigateway.HttpMethod.GET, '/api/admin/incidents/{incidentId}/priority/history'],
      [apigateway.HttpMethod.POST, '/api/admin/incidents/{incidentId}/priority/recalculate'],
      [apigateway.HttpMethod.PATCH, '/api/admin/incidents/{incidentId}/severity'],
      [apigateway.HttpMethod.PATCH, '/api/admin/incidents/{incidentId}/public-impact'],
      [apigateway.HttpMethod.PATCH, '/api/admin/incidents/{incidentId}/hazard-review'],
      [apigateway.HttpMethod.POST, '/api/admin/incidents/{incidentId}/priority/override'],
      [apigateway.HttpMethod.DELETE, '/api/admin/incidents/{incidentId}/priority/override'],
      [apigateway.HttpMethod.GET, '/api/admin/departments/summary'],
      [apigateway.HttpMethod.POST, '/api/admin/departments/seed'],
      [apigateway.HttpMethod.GET, '/api/admin/departments'],
      [apigateway.HttpMethod.POST, '/api/admin/departments'],
      [apigateway.HttpMethod.GET, '/api/admin/departments/{departmentId}'],
      [apigateway.HttpMethod.PATCH, '/api/admin/departments/{departmentId}'],
      [apigateway.HttpMethod.GET, '/api/admin/departments/{departmentId}/officers'],
      [apigateway.HttpMethod.POST, '/api/admin/departments/{departmentId}/officers'],
      [apigateway.HttpMethod.DELETE, '/api/admin/departments/{departmentId}/officers/{officerId}'],
      [apigateway.HttpMethod.GET, '/api/admin/departments/{departmentId}/incidents'],
      [apigateway.HttpMethod.GET, '/api/admin/departments/{departmentId}/history'],
      [apigateway.HttpMethod.GET, '/api/admin/routing-rules'],
      [apigateway.HttpMethod.POST, '/api/admin/routing-rules'],
      [apigateway.HttpMethod.GET, '/api/admin/officers'],
      [apigateway.HttpMethod.GET, '/api/admin/assignments'],
      [apigateway.HttpMethod.GET, '/api/admin/assignments/unassigned'],
      [apigateway.HttpMethod.GET, '/api/admin/incidents/{incidentId}/assignment'],
      [apigateway.HttpMethod.GET, '/api/admin/incidents/{incidentId}/assignment-history'],
      [apigateway.HttpMethod.POST, '/api/admin/incidents/{incidentId}/assign-department'],
      [apigateway.HttpMethod.POST, '/api/admin/incidents/{incidentId}/recommend-officer'],
      [apigateway.HttpMethod.POST, '/api/admin/incidents/{incidentId}/assign-officer'],
      [apigateway.HttpMethod.POST, '/api/admin/incidents/{incidentId}/reassign'],
      [apigateway.HttpMethod.POST, '/api/admin/incidents/{incidentId}/unassign-officer'],
      [apigateway.HttpMethod.GET, '/api/officer/incidents'],
      [apigateway.HttpMethod.GET, '/api/officer/incidents/{incidentId}'],
      [apigateway.HttpMethod.GET, '/api/officer/incidents/{incidentId}/history'],
      [apigateway.HttpMethod.POST, '/api/officer/incidents/{incidentId}/start'],
      [apigateway.HttpMethod.POST, '/api/officer/incidents/{incidentId}/progress'],
      [apigateway.HttpMethod.GET, '/api/officer/incidents/{incidentId}/complaints/{complaintId}/images/{imageId}'],
    ] as const) {
      this.api.addRoutes({ path, methods: [method], authorizer, authorizationScopes: [API_SCOPE],
        integration: new HttpLambdaIntegration(`${method}${path}`, handler, { payloadFormatVersion: apigateway.PayloadFormatVersion.VERSION_2_0 }),
      })
    }
    for (const [verb, path] of [...WORKFLOW_ROUTES, ...ANALYTICS_ROUTES, ...INTELLIGENCE_ROUTES]) {
      this.api.addRoutes({ path, methods: [apigateway.HttpMethod[verb]], authorizer, authorizationScopes: [API_SCOPE], integration: new HttpLambdaIntegration(`${verb}${path}`, handler, { payloadFormatVersion: apigateway.PayloadFormatVersion.VERSION_2_0 }) })
    }
  }
}
