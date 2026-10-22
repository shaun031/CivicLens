import { Match } from 'aws-cdk-lib/assertions'
import { describe, expect, it } from 'vitest'
import { DATABASE_CAPACITY } from '../lib/constructs/database.js'
import { foundation } from './helpers.js'

describe('DynamoDB', () => {
  it('defines four retained Standard tables using default encryption and low provisioned capacity', () => {
    const { template } = foundation()
    template.resourceCountIs('AWS::DynamoDB::Table', 4)
    for (const table of Object.values(template.findResources('AWS::DynamoDB::Table'))) {
      expect(table.DeletionPolicy).toBe('Retain')
      expect(table.UpdateReplacePolicy).toBe('Retain')
      expect(table.Properties).toMatchObject({
        TableClass: 'STANDARD', ProvisionedThroughput: { ReadCapacityUnits: 1, WriteCapacityUnits: 1 },
        SSESpecification: { SSEEnabled: false },
        PointInTimeRecoverySpecification: { PointInTimeRecoveryEnabled: false },
      })
      // CloudFormation defaults omitted BillingMode to PROVISIONED.
      expect(table.Properties.BillingMode ?? 'PROVISIONED').toBe('PROVISIONED')
      expect(table.Properties.StreamSpecification).toBeUndefined()
      expect(table.Properties.AttributeDefinitions.every((attribute: { AttributeType: string }) => attribute.AttributeType === 'S')).toBe(true)
    }
  })

  it('supports complaint lookup, citizen chronology and sparse public geographic indexing', () => {
    const { template } = foundation()
    template.hasResourceProperties('AWS::DynamoDB::Table', {
      KeySchema: [{ AttributeName: 'complaintId', KeyType: 'HASH' }],
      GlobalSecondaryIndexes: [
        { IndexName: 'ByCitizen', KeySchema: [{ AttributeName: 'citizenId', KeyType: 'HASH' }, { AttributeName: 'createdAt', KeyType: 'RANGE' }], Projection: { ProjectionType: 'KEYS_ONLY' }, ProvisionedThroughput: { ReadCapacityUnits: 1, WriteCapacityUnits: 1 } },
        { IndexName: 'ByIncident', KeySchema: [{ AttributeName: 'incidentId', KeyType: 'HASH' }, { AttributeName: 'createdAt', KeyType: 'RANGE' }], Projection: { ProjectionType: 'KEYS_ONLY' }, ProvisionedThroughput: { ReadCapacityUnits: 1, WriteCapacityUnits: 1 } },
        { IndexName: 'PublicGeography', KeySchema: [{ AttributeName: 'publicGeoCell', KeyType: 'HASH' }, { AttributeName: 'publicGeoSortKey', KeyType: 'RANGE' }], Projection: { ProjectionType: 'KEYS_ONLY' }, ProvisionedThroughput: { ReadCapacityUnits: 1, WriteCapacityUnits: 1 } },
        { IndexName: 'InternalGeography', KeySchema: [{ AttributeName: 'internalGeoCell', KeyType: 'HASH' }, { AttributeName: 'internalGeoSortKey', KeyType: 'RANGE' }], Projection: { ProjectionType: 'KEYS_ONLY' }, ProvisionedThroughput: { ReadCapacityUnits: 1, WriteCapacityUnits: 1 } },
        { IndexName: 'MatchingWork', KeySchema: [{ AttributeName: 'matchingPartition', KeyType: 'HASH' }, { AttributeName: 'matchingSortKey', KeyType: 'RANGE' }], Projection: { ProjectionType: 'KEYS_ONLY' }, ProvisionedThroughput: { ReadCapacityUnits: 1, WriteCapacityUnits: 1 } },
      ],
    })
  })

  it('supports incident priority queries and chronological entity audit history', () => {
    const { template } = foundation()
    template.hasResourceProperties('AWS::DynamoDB::Table', {
      KeySchema: [{ AttributeName: 'incidentId', KeyType: 'HASH' }],
      GlobalSecondaryIndexes: [
        Match.objectLike({ IndexName: 'ByCatalog', KeySchema: [{ AttributeName: 'catalogPartition', KeyType: 'HASH' }, { AttributeName: 'catalogSortKey', KeyType: 'RANGE' }], Projection: { ProjectionType: 'KEYS_ONLY' } }),
        Match.objectLike({ IndexName: 'ByStatusPriority', KeySchema: [{ AttributeName: 'status', KeyType: 'HASH' }, { AttributeName: 'prioritySortKey', KeyType: 'RANGE' }] }),
        Match.objectLike({ IndexName: 'ByDepartmentPriority', KeySchema: [{ AttributeName: 'departmentId', KeyType: 'HASH' }, { AttributeName: 'prioritySortKey', KeyType: 'RANGE' }] }),
      ],
    })
    template.hasResourceProperties('AWS::DynamoDB::Table', {
      KeySchema: [{ AttributeName: 'entityId', KeyType: 'HASH' }, { AttributeName: 'timestampEventId', KeyType: 'RANGE' }],
      GlobalSecondaryIndexes: Match.absent(),
    })
  })

  it('keeps all table and GSI capacity at a documented aggregate 13 RCU / 13 WCU', () => {
    const { template } = foundation()
    let totalRcu = 0, totalWcu = 0, indexes = 0
    for (const table of Object.values(template.findResources('AWS::DynamoDB::Table'))) {
      const capacities = [table.Properties.ProvisionedThroughput, ...(table.Properties.GlobalSecondaryIndexes ?? []).map((index: { ProvisionedThroughput: object }) => index.ProvisionedThroughput)]
      indexes += table.Properties.GlobalSecondaryIndexes?.length ?? 0
      for (const capacity of capacities) {
        totalRcu += capacity.ReadCapacityUnits
        totalWcu += capacity.WriteCapacityUnits
      }
    }
    expect({ tables: 4, indexes, totalRcu, totalWcu }).toEqual(DATABASE_CAPACITY)
  })

  it('enables deletion protection for production tables', () => {
    foundation('production').template.allResourcesProperties('AWS::DynamoDB::Table', { DeletionProtectionEnabled: true })
  })
})
