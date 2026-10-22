import { Match } from 'aws-cdk-lib/assertions'
import { describe, expect, it } from 'vitest'
import { foundation } from './helpers.js'
import { loadEnvironment } from '../lib/config/environment.js'

describe('Cognito authentication definitions', () => {
  it('retains exactly one case-insensitive email pool with verification, recovery, and Lite pricing', () => {
    const { template } = foundation()
    template.resourceCountIs('AWS::Cognito::UserPool', 1)
    template.hasResource('AWS::Cognito::UserPool', {
      DeletionPolicy: 'Retain', UpdateReplacePolicy: 'Retain',
      Properties: Match.objectLike({
        UsernameAttributes: ['email'], UsernameConfiguration: { CaseSensitive: false }, AutoVerifiedAttributes: ['email'],
        UserPoolTier: 'LITE', MfaConfiguration: 'OFF',
        AdminCreateUserConfig: { AllowAdminCreateUserOnly: false },
        AccountRecoverySetting: { RecoveryMechanisms: [{ Name: 'verified_email', Priority: 1 }] },
        Policies: { PasswordPolicy: Match.objectLike({ MinimumLength: 12 }) },
      }),
    })
  })
  it('creates exactly CITIZEN, OFFICER, ADMIN groups without user assignments or triggers', () => {
    const { template } = foundation()
    template.resourceCountIs('AWS::Cognito::UserPoolGroup', 3)
    const names = Object.values(template.findResources('AWS::Cognito::UserPoolGroup')).map((group) => group.Properties.GroupName).sort()
    expect(names).toEqual(['ADMIN', 'CITIZEN', 'OFFICER'])
    template.resourceCountIs('AWS::Cognito::UserPoolUser', 0)
    template.resourceCountIs('AWS::Lambda::Function', 4)
    template.hasResourceProperties('AWS::Cognito::UserPool', { LambdaConfig: Match.absent() })
  })
  it('configures a public code-flow client with restricted attributes, revocation, and bounded tokens', () => {
    const { template } = foundation()
    template.resourceCountIs('AWS::Cognito::UserPoolClient', 1)
    template.hasResourceProperties('AWS::Cognito::UserPoolClient', {
      GenerateSecret: false, AllowedOAuthFlows: ['code'], AllowedOAuthFlowsUserPoolClient: true,
      CallbackURLs: ['http://localhost:5173/auth/callback'], LogoutURLs: ['http://localhost:5173/'],
      EnableTokenRevocation: true, PreventUserExistenceErrors: 'ENABLED',
      ReadAttributes: ['email', 'email_verified', 'name'], WriteAttributes: ['email', 'name'],
      AccessTokenValidity: 15, IdTokenValidity: 15, RefreshTokenValidity: 1440,
      TokenValidityUnits: { AccessToken: 'minutes', IdToken: 'minutes', RefreshToken: 'minutes' },
      AllowedOAuthScopes: ['openid', 'email', 'profile', 'aws.cognito.signin.user.admin', {
        'Fn::Join': ['', [{ Ref: Match.anyValue() }, '/access']],
      }],
    })
    template.hasResourceProperties('AWS::Cognito::UserPoolResourceServer', {
      Identifier: 'civiclens', Scopes: [Match.objectLike({ ScopeName: 'access' })],
    })
    template.resourceCountIs('AWS::Cognito::UserPoolDomain', 1)
    expect(template.toJSON().Outputs).toHaveProperty('CognitoIssuer')
    expect(template.toJSON().Outputs).toHaveProperty('CognitoClientId')
  })
  it('uses an HTTP API JWT authorizer and API access scopes on every protected route', () => {
    const { template } = foundation()
    template.resourceCountIs('AWS::ApiGatewayV2::Authorizer', 1)
    template.hasResourceProperties('AWS::ApiGatewayV2::Authorizer', {
      AuthorizerType: 'JWT', IdentitySource: ['$request.header.Authorization'],
      JwtConfiguration: { Audience: [{ Ref: Match.anyValue() }], Issuer: Match.anyValue() },
    })
    for (const key of ['GET /api/auth/me', 'PATCH /api/profile', 'GET /api/portal/citizen', 'GET /api/portal/officer', 'GET /api/portal/admin', 'POST /api/complaints', 'GET /api/complaints', 'GET /api/complaints/summary', 'GET /api/complaints/{complaintId}', 'GET /api/complaints/{complaintId}/images/{imageId}', 'PATCH /api/complaints/{complaintId}/publication-request', 'PATCH /api/admin/complaints/{complaintId}/publication']) {
      template.hasResourceProperties('AWS::ApiGatewayV2::Route', {
        RouteKey: key, AuthorizationType: 'JWT', AuthorizerId: { Ref: Match.anyValue() }, AuthorizationScopes: ['civiclens/access'],
      })
    }
  })
  it('validates callback/logout URLs and reserves production placeholders for offline synthesis only', () => {
    expect(loadEnvironment({ stage: 'production' }).callbackUrls).toEqual(['https://frontend.example.invalid/auth/callback'])
    for (const callbackUrls of [['http://example.org/auth/callback'], ['https://*.example.org/'], ['https://example.org/#fragment'], []]) {
      expect(() => loadEnvironment({ stage: 'production', callbackUrls })).toThrow()
    }
  })
})
