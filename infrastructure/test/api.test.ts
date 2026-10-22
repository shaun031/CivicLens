import { Match } from 'aws-cdk-lib/assertions'
import { describe, it } from 'vitest'
import { foundation } from './helpers.js'

describe('HTTP API', () => {
  it('keeps health public while adding explicit JWT-protected identity routes', () => {
    const { template } = foundation()
    template.hasResourceProperties('AWS::ApiGatewayV2::Api', {
      ProtocolType: 'HTTP', CorsConfiguration: {
        AllowMethods: ['GET', 'PATCH', 'POST', 'DELETE', 'PUT'], AllowOrigins: ['http://localhost:5173', 'http://127.0.0.1:5173'],
        AllowHeaders: ['content-type', 'authorization', 'idempotency-key'], AllowCredentials: false, MaxAge: 600,
      },
    })
    template.resourceCountIs('AWS::ApiGatewayV2::Route', 133)
    template.hasResourceProperties('AWS::ApiGatewayV2::Route', { RouteKey: 'GET /api/health', AuthorizationType: 'NONE', Target: Match.anyValue() })
    template.hasResourceProperties('AWS::ApiGatewayV2::Integration', {
      IntegrationType: 'AWS_PROXY', PayloadFormatVersion: '2.0', IntegrationUri: { 'Fn::GetAtt': [Match.anyValue(), 'Arn'] },
    })
    template.hasResourceProperties('AWS::Lambda::Permission', {
      Action: 'lambda:InvokeFunction', Principal: 'apigateway.amazonaws.com', SourceArn: Match.anyValue(),
    })
    template.resourceCountIs('AWS::ApiGatewayV2::DomainName', 0)
  })

  it('uses configured HTTPS origins for production and no wildcard default', () => {
    foundation('production', ['https://civic.example.org']).template.hasResourceProperties('AWS::ApiGatewayV2::Api', {
      CorsConfiguration: Match.objectLike({ AllowOrigins: ['https://civic.example.org'], AllowMethods: ['GET', 'PATCH', 'POST', 'DELETE', 'PUT'] }),
    })
    foundation('production').template.hasResourceProperties('AWS::ApiGatewayV2::Api', { CorsConfiguration: Match.absent() })
  })
})
