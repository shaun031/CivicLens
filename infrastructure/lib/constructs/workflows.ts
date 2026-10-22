import { Duration, RemovalPolicy } from 'aws-cdk-lib'
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb'
import * as events from 'aws-cdk-lib/aws-events'
import * as targets from 'aws-cdk-lib/aws-events-targets'
import * as iam from 'aws-cdk-lib/aws-iam'
import * as logs from 'aws-cdk-lib/aws-logs'
import * as sources from 'aws-cdk-lib/aws-lambda-event-sources'
import * as sns from 'aws-cdk-lib/aws-sns'
import * as sqs from 'aws-cdk-lib/aws-sqs'
import * as sfn from 'aws-cdk-lib/aws-stepfunctions'
import * as tasks from 'aws-cdk-lib/aws-stepfunctions-tasks'
import type * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch'
import { Construct } from 'constructs'
import { BackendLambda } from './backend-lambda.js'
import { INTELLIGENCE_EVENTS } from '../intelligence-routes.js'
import type { CivicLensStack } from '../stacks/civiclens-stack.js'
import type { CloudStage, EnvironmentConfig } from '../config/environment.js'

export class Workflows extends Construct {
  readonly table: dynamodb.Table
  readonly bus: events.EventBus
  readonly processing: sqs.Queue
  readonly notifications: sqs.Queue
  readonly alerts: sns.Topic
  readonly machine: sfn.StateMachine
  readonly metrics: Readonly<Record<string, cloudwatch.Metric>>
  constructor(scope: CivicLensStack, id: string, config: EnvironmentConfig & { stage: CloudStage }) {
    super(scope, id)
    this.table = new dynamodb.Table(this, 'Operations', {
      partitionKey: { name: 'pk', type: dynamodb.AttributeType.STRING }, sortKey: { name: 'sk', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PROVISIONED, readCapacity: 1, writeCapacity: 1,
      tableClass: dynamodb.TableClass.STANDARD,
      encryption: dynamodb.TableEncryption.DEFAULT, removalPolicy: RemovalPolicy.RETAIN, deletionProtection: config.stage === 'production',
      pointInTimeRecoverySpecification: { pointInTimeRecoveryEnabled: false },
    })
    this.table.addGlobalSecondaryIndex({ indexName: 'ByQueue', partitionKey: { name: 'queue', type: dynamodb.AttributeType.STRING }, sortKey: { name: 'due', type: dynamodb.AttributeType.STRING }, projectionType: dynamodb.ProjectionType.KEYS_ONLY, readCapacity: 1, writeCapacity: 1 })
    this.bus = new events.EventBus(this, 'DomainBus', { eventBusName: `civiclens-${config.stage}-domain` })
    this.alerts = new sns.Topic(this, 'OperationalAlerts', { displayName: 'CivicLens explicitly opted-in operational alerts' })
    const queue = (name: string) => {
      const dead = new sqs.Queue(this, `${name}Dead`, { encryption: sqs.QueueEncryption.SQS_MANAGED, retentionPeriod: Duration.days(14) })
      return new sqs.Queue(this, name, { encryption: sqs.QueueEncryption.SQS_MANAGED, visibilityTimeout: Duration.seconds(600), retentionPeriod: Duration.days(4), receiveMessageWaitTime: Duration.seconds(20), deadLetterQueue: { queue: dead, maxReceiveCount: 5 } })
    }
    this.processing = queue('Processing'); this.notifications = queue('Notifications')
    const processingTypes = ['ComplaintSubmitted', 'IncidentMembershipChanged']
    const notificationTypes = ['IncidentPriorityChanged', 'IncidentDepartmentAssigned', 'IncidentOfficerAssigned', 'IncidentOfficerReassigned', 'IncidentWorkStarted', 'IncidentProgressUpdated', 'IncidentStatusChanged', 'IncidentOverdue', 'DuplicateReviewRequired', 'RoutingReviewRequired', 'WorkflowFailed', ...INTELLIGENCE_EVENTS]
    for (const [name, types, destination] of [['ProcessingEvents', processingTypes, this.processing], ['NotificationEvents', notificationTypes, this.notifications]] as const) {
      new events.Rule(this, name, { eventBus: this.bus, eventPattern: { source: ['civiclens.domain'], detailType: [...types], detail: { eventVersion: [1] } }, targets: [new targets.SqsQueue(destination, { retryAttempts: 3, maxEventAge: Duration.hours(2), deadLetterQueue: destination.deadLetterQueue!.queue })] })
    }
    const worker = (name: string, handler: string, seconds: number) => {
      const group = new logs.LogGroup(this, `${name}Logs`, { retention: logs.RetentionDays.ONE_WEEK, removalPolicy: RemovalPolicy.RETAIN })
      const fn = new BackendLambda(this, name, { stage: config.stage, frontendOrigins: config.frontendOrigins, database: scope.database, storage: scope.storage, authentication: scope.authentication, logGroup: group, entrypoint: handler, timeoutSeconds: seconds, reservedConcurrency: name === 'Consumer' ? 4 : name === 'Step' ? 2 : 1 }).handler
      scope.permissions.grantProcessingWorker(fn)
      return fn
    }
    const consume = worker('Consumer', 'app.workflow_handlers.sqs_handler', 90)
    const step = worker('Step', 'app.workflow_handlers.step_handler', 30)
    const scheduled = worker('Scheduled', 'app.workflow_handlers.scheduled_handler', 90)
    for (const destination of [this.processing, this.notifications]) consume.addEventSource(new sources.SqsEventSource(destination, { batchSize: 1, maxConcurrency: 2, reportBatchItemFailures: true }))
    const failed = new sfn.Fail(this, 'Failed', { error: 'TRIAGE_FAILED', cause: 'Recorded for administrator review' })
    const recordFailure = new tasks.LambdaInvoke(this, 'RecordFailure', { lambdaFunction: step, payload: sfn.TaskInput.fromObject({ 'event.$': '$.event', 'execution.$': '$.execution', 'errorCategory.$': '$.safeFailure.Error', step: 'RecordFailure' }), payloadResponseOnly: true, retryOnServiceExceptions: false })
    recordFailure.addCatch(failed, { errors: ['States.ALL'], resultPath: sfn.JsonPath.DISCARD }); recordFailure.next(failed)
    const task = (name: string) => {
      const node = new tasks.LambdaInvoke(this, name, { lambdaFunction: step, payload: sfn.TaskInput.fromObject({ 'event.$': '$.event', 'execution.$': '$.execution', step: name }), payloadResponseOnly: true, retryOnServiceExceptions: false })
      node.addRetry({ errors: ['TransientWorkflowError', 'Lambda.ServiceException', 'Lambda.TooManyRequestsException'], interval: Duration.seconds(2), backoffRate: 2, maxAttempts: 3 })
      node.addCatch(recordFailure, { errors: ['States.ALL'], resultPath: '$.safeFailure' }); return node
    }
    const complete = task('CompleteWorkflow').next(new sfn.Succeed(this, 'Succeeded'))
    const notify = task('EvaluateNotifications').next(complete)
    const route = task('RouteDepartment').next(notify)
    const priority = task('RecalculatePriority').next(route)
    const review = new sfn.Choice(this, 'ReviewRequired').when(sfn.Condition.booleanEquals('$.execution.reviewRequired', true), priority).otherwise(priority)
    const cluster = task('EvaluateClustering').next(review)
    const matching = task('RunDuplicateDetection').next(cluster)
    const eligibility = new sfn.Choice(this, 'EligibleComplaint').when(sfn.Condition.booleanEquals('$.execution.eligible', true), matching).otherwise(complete)
    const validate = task('ValidateComplaint').next(eligibility)
    const initialize = new sfn.Pass(this, 'Initialize', { parameters: { 'event.$': '$.event', execution: {} } }).next(validate)
    this.machine = new sfn.StateMachine(this, 'IncidentTriage', { stateMachineType: sfn.StateMachineType.STANDARD, definitionBody: sfn.DefinitionBody.fromChainable(initialize), timeout: Duration.minutes(5), tracingEnabled: false })
    // Basic service metrics only: these descriptors create no alarms, dashboards or custom metrics.
    this.metrics = Object.freeze({
      processingBacklog: this.processing.metricApproximateNumberOfMessagesVisible(),
      processingDeadLetters: this.processing.deadLetterQueue!.queue.metricApproximateNumberOfMessagesVisible(),
      notificationBacklog: this.notifications.metricApproximateNumberOfMessagesVisible(),
      notificationDeadLetters: this.notifications.deadLetterQueue!.queue.metricApproximateNumberOfMessagesVisible(),
      consumerErrors: consume.metricErrors(), stepErrors: step.metricErrors(),
      executionFailures: this.machine.metricFailed(),
      maximumStepDuration: step.metricDuration({ statistic: 'Maximum' }),
      scheduledCheckErrors: scheduled.metricErrors(),
    })
    consume.addToRolePolicy(new iam.PolicyStatement({ actions: ['states:StartExecution'], resources: [this.machine.stateMachineArn] }))
    for (const fn of [scope.backend.handler, consume, step, scheduled]) {
      fn.addEnvironment('WORKFLOW_TABLE_NAME', this.table.tableName); fn.addEnvironment('EVENT_BUS_NAME', this.bus.eventBusName)
      fn.addEnvironment('OPERATIONAL_ALERT_TOPIC_ARN', this.alerts.topicArn); fn.addEnvironment('OPERATIONAL_ALERTS_ENABLED', 'false')
      fn.addToRolePolicy(new iam.PolicyStatement({ actions: ['dynamodb:GetItem', 'dynamodb:PutItem', 'dynamodb:UpdateItem', 'dynamodb:ConditionCheckItem'], resources: [this.table.tableArn] }))
      fn.addToRolePolicy(new iam.PolicyStatement({ actions: ['dynamodb:Query'], resources: [`${this.table.tableArn}/index/ByQueue`] }))
    }
    consume.addEnvironment('TRIAGE_STATE_MACHINE_ARN', this.machine.stateMachineArn)
    scheduled.addToRolePolicy(new iam.PolicyStatement({ actions: ['events:PutEvents'], resources: [this.bus.eventBusArn] }))
    step.addToRolePolicy(new iam.PolicyStatement({ actions: ['sns:Publish'], resources: [this.alerts.topicArn] }))
    new events.Rule(this, 'HourlyChecks', { enabled: false, schedule: events.Schedule.rate(Duration.hours(1)), targets: [new targets.LambdaFunction(scheduled, { event: events.RuleTargetInput.fromObject({ batchSize: 20 }), retryAttempts: 2, maxEventAge: Duration.hours(1) })] })
  }
}
