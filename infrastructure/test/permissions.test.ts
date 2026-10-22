import { Role, ServicePrincipal } from 'aws-cdk-lib/aws-iam'
import { Template } from 'aws-cdk-lib/assertions'
import { describe, expect, it } from 'vitest'
import { foundation } from './helpers.js'

describe('Future opt-in permissions', () => {
  it('scopes audit writes and evidence GET/PUT without granting delete or list', () => {
    const { stack } = foundation()
    const worker = new Role(stack, 'FutureWorker', { assumedBy: new ServicePrincipal('lambda.amazonaws.com') })
    stack.permissions.grantAuditAppend(worker)
    stack.permissions.grantEvidenceRead(worker)
    stack.permissions.grantEvidenceUpload(worker)
    const policies = Object.entries(Template.fromStack(stack).findResources('AWS::IAM::Policy')).filter(([id]) => id.startsWith('FutureWorker')).map(([, policy]) => policy)
    const serialized = JSON.stringify(policies)
    expect(serialized).toContain('dynamodb:PutItem')
    expect(serialized).toContain('s3:GetObject')
    expect(serialized).toContain('s3:PutObject')
    expect(serialized).toContain('/complaints/*')
    expect(serialized).not.toMatch(/DeleteItem|DeleteObject|ListBucket|s3:\*|dynamodb:\*/)
  })

  it('scopes complaint and incident reads/writes to their tables and queryable indexes', () => {
    const { stack } = foundation()
    const worker = new Role(stack, 'FutureWorker', { assumedBy: new ServicePrincipal('lambda.amazonaws.com') })
    stack.permissions.grantComplaintRead(worker)
    stack.permissions.grantComplaintWrite(worker)
    stack.permissions.grantIncidentRead(worker)
    stack.permissions.grantIncidentWrite(worker)
    const policies = Object.entries(Template.fromStack(stack).findResources('AWS::IAM::Policy')).filter(([id]) => id.startsWith('FutureWorker')).map(([, policy]) => policy)
    const serialized = JSON.stringify(policies)
    expect(serialized).toContain('dynamodb:Query')
    expect(serialized).not.toContain('/index/*')
    expect(serialized).toContain('/index/ByCitizen')
    expect(serialized).toContain('/index/ByCatalog')
    expect(serialized).toContain('dynamodb:UpdateItem')
    expect(serialized).not.toMatch(/DeleteItem|Scan|dynamodb:\*|s3:/)
  })
})
