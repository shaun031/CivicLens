import { Duration, RemovalPolicy } from 'aws-cdk-lib'
import * as s3 from 'aws-cdk-lib/aws-s3'
import { Construct } from 'constructs'

export class Storage extends Construct {
  readonly evidence: s3.Bucket

  constructor(scope: Construct, id: string, frontendOrigins: readonly string[]) {
    super(scope, id)
    this.evidence = new s3.Bucket(this, 'Evidence', {
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      enforceSSL: true,
      objectOwnership: s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
      removalPolicy: RemovalPolicy.RETAIN,
      autoDeleteObjects: false,
      versioned: false,
      cors: frontendOrigins.length ? [{
        allowedOrigins: [...frontendOrigins],
        allowedMethods: [s3.HttpMethods.GET, s3.HttpMethods.PUT],
        allowedHeaders: ['content-type'],
        exposedHeaders: ['ETag'],
        maxAge: Duration.minutes(10).toSeconds(),
      }] : undefined,
    })
  }
}
