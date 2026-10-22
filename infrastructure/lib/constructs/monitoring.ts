import { RemovalPolicy } from 'aws-cdk-lib'
import * as logs from 'aws-cdk-lib/aws-logs'
import { Construct } from 'constructs'
import type { CloudStage } from '../config/environment.js'

export class Monitoring extends Construct {
  readonly backendLogs: logs.LogGroup

  constructor(scope: Construct, id: string, stage: CloudStage) {
    super(scope, id)
    this.backendLogs = new logs.LogGroup(this, 'BackendLogs', {
      logGroupName: `/civiclens/${stage}/backend`,
      retention: logs.RetentionDays.ONE_WEEK,
      removalPolicy: RemovalPolicy.RETAIN,
    })
  }
}
