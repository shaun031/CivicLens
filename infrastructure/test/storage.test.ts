import { Match } from 'aws-cdk-lib/assertions'
import { describe, expect, it } from 'vitest'
import { foundation } from './helpers.js'

describe('Evidence storage', () => {
  it('defines one retained private SSE-S3 bucket with owner-enforced ownership', () => {
    const { template } = foundation()
    template.resourceCountIs('AWS::S3::Bucket', 1)
    template.hasResource('AWS::S3::Bucket', {
      DeletionPolicy: 'Retain', UpdateReplacePolicy: 'Retain',
      Properties: Match.objectLike({
        BucketEncryption: { ServerSideEncryptionConfiguration: [{ ServerSideEncryptionByDefault: { SSEAlgorithm: 'AES256' } }] },
        PublicAccessBlockConfiguration: { BlockPublicAcls: true, BlockPublicPolicy: true, IgnorePublicAcls: true, RestrictPublicBuckets: true },
        OwnershipControls: { Rules: [{ ObjectOwnership: 'BucketOwnerEnforced' }] },
        BucketName: Match.absent(), AccessControl: Match.absent(), ReplicationConfiguration: Match.absent(), VersioningConfiguration: Match.absent(),
      }),
    })
    template.hasResourceProperties('AWS::S3::BucketPolicy', {
      PolicyDocument: Match.objectLike({ Statement: Match.arrayWith([Match.objectLike({
        Effect: 'Deny', Principal: { AWS: '*' }, Action: 's3:*', Condition: { Bool: { 'aws:SecureTransport': 'false' } },
      })]) }),
    })
    for (const policy of Object.values(template.findResources('AWS::S3::BucketPolicy'))) {
      expect(policy.Properties.PolicyDocument.Statement.every((statement: { Effect: string }) => statement.Effect === 'Deny')).toBe(true)
    }
  })

  it('limits CORS to exact origins and GET/PUT, omitting CORS for unconfigured production', () => {
    foundation('demo', ['http://localhost:5173']).template.hasResourceProperties('AWS::S3::Bucket', {
      CorsConfiguration: { CorsRules: [{ AllowedOrigins: ['http://localhost:5173'], AllowedMethods: ['GET', 'PUT'], AllowedHeaders: ['content-type'], ExposedHeaders: ['ETag'], MaxAge: 600 }] },
    })
    foundation('production').template.hasResourceProperties('AWS::S3::Bucket', { CorsConfiguration: Match.absent() })
  })
})
