import * as iam from 'aws-cdk-lib/aws-iam'
import type { Database } from './constructs/database.js'
import type { Storage } from './constructs/storage.js'

/** Opt-in grants for later handlers. None is applied to the Phase 1 health function. */
export class ApplicationPermissions {
  constructor(private readonly database: Database, private readonly storage: Storage) {}

  grantComplaintBackend(grantee: iam.IGrantable): void {
    // Transactional Put/Update also authorize idempotency, per-citizen summaries and rate keys.
    iam.Grant.addToPrincipal({ grantee, actions: ['dynamodb:GetItem', 'dynamodb:BatchGetItem', 'dynamodb:PutItem', 'dynamodb:UpdateItem', 'dynamodb:ConditionCheckItem'], resourceArns: [this.database.complaints.tableArn] })
    iam.Grant.addToPrincipal({ grantee, actions: ['dynamodb:GetItem', 'dynamodb:PutItem', 'dynamodb:UpdateItem', 'dynamodb:ConditionCheckItem'], resourceArns: [this.database.incidents.tableArn] })
    iam.Grant.addToPrincipal({ grantee, actions: ['dynamodb:Query'], resourceArns: [`${this.database.incidents.tableArn}/index/ByCatalog`] })
    iam.Grant.addToPrincipal({ grantee, actions: ['dynamodb:Query'], resourceArns: [`${this.database.incidents.tableArn}/index/ByStatusPriority`] })
    iam.Grant.addToPrincipal({ grantee, actions: ['dynamodb:Query'], resourceArns: [`${this.database.incidents.tableArn}/index/ByDepartmentPriority`] })
    iam.Grant.addToPrincipal({ grantee, actions: ['dynamodb:Query'], resourceArns: [this.database.auditEvents.tableArn] })
    iam.Grant.addToPrincipal({ grantee, actions: ['dynamodb:Query'], resourceArns: [`${this.database.complaints.tableArn}/index/ByCitizen`] })
    iam.Grant.addToPrincipal({ grantee, actions: ['dynamodb:Query'], resourceArns: [`${this.database.complaints.tableArn}/index/PublicGeography`] })
    iam.Grant.addToPrincipal({ grantee, actions: ['dynamodb:Query'], resourceArns: [`${this.database.complaints.tableArn}/index/InternalGeography`] })
    iam.Grant.addToPrincipal({ grantee, actions: ['dynamodb:Query'], resourceArns: [`${this.database.complaints.tableArn}/index/MatchingWork`] })
    iam.Grant.addToPrincipal({ grantee, actions: ['dynamodb:PutItem'], resourceArns: [this.database.auditEvents.tableArn] })
    iam.Grant.addToPrincipal({ grantee, actions: ['s3:GetObject', 's3:PutObject', 's3:DeleteObject'], resourceArns: [this.storage.evidence.arnForObjects('complaints/*')] })
  }

  grantComplaintRead(grantee: iam.IGrantable): iam.Grant {
    // Existing API-specific grants remain separate from the processing role below.
    iam.Grant.addToPrincipal({ grantee, actions: ['dynamodb:Query'], resourceArns: [`${this.database.complaints.tableArn}/index/ByCitizen`] })
    return iam.Grant.addToPrincipal({ grantee, actions: ['dynamodb:GetItem', 'dynamodb:BatchGetItem'], resourceArns: [this.database.complaints.tableArn] })
  }

  grantProcessingWorker(grantee: iam.IGrantable): void {
    for (const table of [this.database.complaints, this.database.incidents]) {
      iam.Grant.addToPrincipal({ grantee, actions: ['dynamodb:GetItem', 'dynamodb:PutItem', 'dynamodb:UpdateItem', 'dynamodb:ConditionCheckItem'], resourceArns: [table.tableArn] })
    }
    for (const index of ['InternalGeography', 'MatchingWork']) iam.Grant.addToPrincipal({ grantee, actions: ['dynamodb:Query'], resourceArns: [`${this.database.complaints.tableArn}/index/${index}`] })
    for (const index of ['ByCatalog', 'ByStatusPriority', 'ByDepartmentPriority']) iam.Grant.addToPrincipal({ grantee, actions: ['dynamodb:Query'], resourceArns: [`${this.database.incidents.tableArn}/index/${index}`] })
    iam.Grant.addToPrincipal({ grantee, actions: ['dynamodb:PutItem', 'dynamodb:Query'], resourceArns: [this.database.auditEvents.tableArn] })
    iam.Grant.addToPrincipal({ grantee, actions: ['s3:GetObject'], resourceArns: [this.storage.evidence.arnForObjects('complaints/*')] })
  }

  grantComplaintWrite(grantee: iam.IGrantable): iam.Grant {
    return iam.Grant.addToPrincipal({ grantee, actions: ['dynamodb:PutItem', 'dynamodb:UpdateItem'], resourceArns: [this.database.complaints.tableArn] })
  }

  grantIncidentRead(grantee: iam.IGrantable): iam.Grant {
    iam.Grant.addToPrincipal({ grantee, actions: ['dynamodb:Query'], resourceArns: [`${this.database.incidents.tableArn}/index/ByCatalog`] })
    return iam.Grant.addToPrincipal({ grantee, actions: ['dynamodb:GetItem', 'dynamodb:BatchGetItem'], resourceArns: [this.database.incidents.tableArn] })
  }

  grantIncidentWrite(grantee: iam.IGrantable): iam.Grant {
    return iam.Grant.addToPrincipal({ grantee, actions: ['dynamodb:PutItem', 'dynamodb:UpdateItem'], resourceArns: [this.database.incidents.tableArn] })
  }

  grantAuditAppend(grantee: iam.IGrantable): iam.Grant {
    return this.database.auditEvents.grant(grantee, 'dynamodb:PutItem')
  }

  grantEvidenceRead(grantee: iam.IGrantable): iam.Grant {
    return iam.Grant.addToPrincipal({
      grantee, actions: ['s3:GetObject'], resourceArns: [this.storage.evidence.arnForObjects('complaints/*')],
    })
  }

  grantEvidenceUpload(grantee: iam.IGrantable): iam.Grant {
    return iam.Grant.addToPrincipal({
      grantee, actions: ['s3:PutObject'], resourceArns: [this.storage.evidence.arnForObjects('complaints/*')],
    })
  }
}
