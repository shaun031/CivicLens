import { Aws, Duration, RemovalPolicy } from 'aws-cdk-lib'
import * as cognito from 'aws-cdk-lib/aws-cognito'
import { Construct } from 'constructs'
import type { EnvironmentConfig } from '../config/environment.js'

export const API_SCOPE = 'civiclens/access'

export class Authentication extends Construct {
  readonly userPool: cognito.UserPool
  readonly client: cognito.UserPoolClient
  readonly domain: cognito.UserPoolDomain
  readonly issuer: string

  constructor(scope: Construct, id: string, config: EnvironmentConfig) {
    super(scope, id)
    this.userPool = new cognito.UserPool(this, 'UserPool', {
      signInAliases: { email: true }, signInCaseSensitive: false,
      selfSignUpEnabled: true, autoVerify: { email: true },
      standardAttributes: { email: { required: true, mutable: false }, fullname: { required: true, mutable: true } },
      passwordPolicy: { minLength: 12, requireLowercase: false, requireUppercase: false, requireDigits: false, requireSymbols: false, tempPasswordValidity: Duration.days(1) },
      accountRecovery: cognito.AccountRecovery.EMAIL_ONLY,
      mfa: cognito.Mfa.OFF,
      featurePlan: cognito.FeaturePlan.LITE,
      removalPolicy: RemovalPolicy.RETAIN,
      deletionProtection: config.stage === 'production',
    })
    const accessScope = new cognito.ResourceServerScope({ scopeName: 'access', scopeDescription: 'Access CivicLens APIs as an authenticated user; role checks are enforced separately' })
    const server = this.userPool.addResourceServer('ApiResourceServer', { identifier: 'civiclens', scopes: [accessScope] })
    this.client = this.userPool.addClient('BrowserClient', {
      generateSecret: false,
      authFlows: { userPassword: false, userSrp: false, adminUserPassword: false, custom: false },
      preventUserExistenceErrors: true, enableTokenRevocation: true,
      accessTokenValidity: Duration.minutes(15), idTokenValidity: Duration.minutes(15), refreshTokenValidity: Duration.days(1),
      oAuth: {
        flows: { authorizationCodeGrant: true, implicitCodeGrant: false, clientCredentials: false },
        callbackUrls: [...config.callbackUrls], logoutUrls: [...config.logoutUrls],
        scopes: [cognito.OAuthScope.OPENID, cognito.OAuthScope.EMAIL, cognito.OAuthScope.PROFILE, cognito.OAuthScope.COGNITO_ADMIN, cognito.OAuthScope.resourceServer(server, accessScope)],
      },
      readAttributes: new cognito.ClientAttributes().withStandardAttributes({ email: true, emailVerified: true, fullname: true }),
      writeAttributes: new cognito.ClientAttributes().withStandardAttributes({ email: true, fullname: true }),
      supportedIdentityProviders: [cognito.UserPoolClientIdentityProvider.COGNITO],
    })
    this.domain = this.userPool.addDomain('LoginDomain', {
      cognitoDomain: { domainPrefix: `civiclens-${config.stage}-${Aws.ACCOUNT_ID}-${Aws.REGION}` },
      managedLoginVersion: cognito.ManagedLoginVersion.CLASSIC_HOSTED_UI,
    })
    for (const group of ['CITIZEN', 'OFFICER', 'ADMIN']) {
      new cognito.CfnUserPoolGroup(this, `${group}Group`, { userPoolId: this.userPool.userPoolId, groupName: group, description: `Trusted provisioning only: ${group}` })
    }
    // Explicit HTTPS issuer; do not depend on ambiguous ProviderURL return formatting.
    this.issuer = `https://cognito-idp.${Aws.REGION}.${Aws.URL_SUFFIX}/${this.userPool.userPoolId}`
  }
}
