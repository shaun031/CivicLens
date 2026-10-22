import { RemovalPolicy } from 'aws-cdk-lib'
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb'
import { Construct } from 'constructs'

/** Three base tables + eight GSIs, each at 1 RCU / 1 WCU. */
export const DATABASE_CAPACITY = Object.freeze({ tables: 4, indexes: 9, totalRcu: 13, totalWcu: 13 })

export class Database extends Construct {
  readonly complaints: dynamodb.Table
  readonly incidents: dynamodb.Table
  readonly auditEvents: dynamodb.Table

  constructor(scope: Construct, id: string, production: boolean) {
    super(scope, id)
    const defaults: Omit<dynamodb.TableProps, 'partitionKey'> = {
      billingMode: dynamodb.BillingMode.PROVISIONED,
      tableClass: dynamodb.TableClass.STANDARD,
      readCapacity: 1,
      writeCapacity: 1,
      encryption: dynamodb.TableEncryption.DEFAULT,
      removalPolicy: RemovalPolicy.RETAIN,
      deletionProtection: production,
      pointInTimeRecoverySpecification: { pointInTimeRecoveryEnabled: false },
    }
    this.complaints = new dynamodb.Table(this, 'Complaints', {
      ...defaults,
      partitionKey: { name: 'complaintId', type: dynamodb.AttributeType.STRING },
    })
    this.incidents = new dynamodb.Table(this, 'Incidents', {
      ...defaults,
      partitionKey: { name: 'incidentId', type: dynamodb.AttributeType.STRING },
    })
    this.auditEvents = new dynamodb.Table(this, 'AuditEvents', {
      ...defaults,
      partitionKey: { name: 'entityId', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'timestampEventId', type: dynamodb.AttributeType.STRING },
    })
    for (const [indexName, partitionKey] of [['ByCitizen', 'citizenId'], ['ByIncident', 'incidentId']]) {
      this.complaints.addGlobalSecondaryIndex({
        indexName,
        partitionKey: { name: partitionKey, type: dynamodb.AttributeType.STRING },
        sortKey: { name: 'createdAt', type: dynamodb.AttributeType.STRING },
        projectionType: dynamodb.ProjectionType.KEYS_ONLY,
        readCapacity: 1,
        writeCapacity: 1,
      })
    }
    // Only sanitized approved public projection items carry these attributes.
    this.complaints.addGlobalSecondaryIndex({
      indexName: 'PublicGeography',
      partitionKey: { name: 'publicGeoCell', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'publicGeoSortKey', type: dynamodb.AttributeType.STRING },
      projectionType: dynamodb.ProjectionType.KEYS_ONLY,
      readCapacity: 1,
      writeCapacity: 1,
    })
    // Internal indexes include PRIVATE complaints; never reuse the public projection index.
    // Namespaced jobs/candidates share one sparse work index without adding another table.
    for (const [indexName, partitionKey, sortKey] of [
      ['InternalGeography', 'internalGeoCell', 'internalGeoSortKey'],
      ['MatchingWork', 'matchingPartition', 'matchingSortKey'],
    ]) {
      this.complaints.addGlobalSecondaryIndex({
        indexName,
        partitionKey: { name: partitionKey, type: dynamodb.AttributeType.STRING },
        sortKey: { name: sortKey, type: dynamodb.AttributeType.STRING },
        projectionType: dynamodb.ProjectionType.KEYS_ONLY,
        readCapacity: 1, writeCapacity: 1,
      })
    }
    // Membership administration must not depend on a fake pre-Phase8 priority sort key.
    this.incidents.addGlobalSecondaryIndex({
      indexName: 'ByCatalog',
      partitionKey: { name: 'catalogPartition', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'catalogSortKey', type: dynamodb.AttributeType.STRING },
      projectionType: dynamodb.ProjectionType.KEYS_ONLY,
      readCapacity: 1, writeCapacity: 1,
    })
    // Phase8/9 use sparse namespaced priority and work sidecars on existing indexes.
    for (const [indexName, partitionKey] of [['ByStatusPriority', 'status'], ['ByDepartmentPriority', 'departmentId']]) {
      this.incidents.addGlobalSecondaryIndex({
        indexName,
        partitionKey: { name: partitionKey, type: dynamodb.AttributeType.STRING },
        sortKey: { name: 'prioritySortKey', type: dynamodb.AttributeType.STRING },
        projectionType: dynamodb.ProjectionType.KEYS_ONLY,
        readCapacity: 1,
        writeCapacity: 1,
      })
    }
  }
}
