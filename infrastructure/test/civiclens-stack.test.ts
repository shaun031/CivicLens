import { readFileSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { createCdkApp } from '../lib/app.js'
import { assertDeploymentReadiness, assertFoundationSafety, type FoundationTemplate } from '../lib/safety.js'
import { foundation } from './helpers.js'

describe('CivicLens Phase 1 foundation', () => {
  it.each(['demo', 'production'] as const)('synthesizes %s with expected resources and a deployment block', (stage) => {
    const { app, template } = foundation(stage)
    expect(app.synth().getStackArtifact(`CivicLens-${stage}`)).toBeDefined()
    assertFoundationSafety(template.toJSON() as FoundationTemplate)
    expect(template.toJSON().Rules.DeploymentBlockedUntilPhase14).toEqual({
      Assertions: [{
        Assert: { 'Fn::Equals': ['PHASE_1_SYNTHESIS_ONLY', 'PHASE_14_APPROVED_READY_ARTIFACT'] },
        AssertDescription: 'Deployment is blocked: Phase 14 approval and a verified Linux Lambda artifact are required.',
      }],
    })
    expect(Object.keys(template.toJSON().Outputs)).toEqual(expect.arrayContaining([
      'ApiEndpointUrl', 'LambdaFunctionName', 'ComplaintsTableName', 'IncidentsTableName',
      'AuditEventsTableName', 'EvidenceBucketName', 'DeploymentStage',
    ]))
  })

  it('creates no cloud stack for local', () => {
    expect(createCdkApp({ context: { stage: 'local' } }).synth().stacks).toHaveLength(0)
  })

  it('stages only Python application files, without secrets or Windows dependencies', () => {
    const assembly = foundation().app.synth()
    const manifest = JSON.parse(readFileSync(resolve(assembly.directory, 'CivicLens-demo.assets.json'), 'utf8')) as {
      files: Record<string, { source: { path: string } }>
    }
    const asset = Object.values(manifest.files).find((entry) => !entry.source.path.endsWith('.template.json'))
    expect(asset).toBeDefined()
    const directory = resolve(assembly.directory, asset!.source.path)
    const files = readdirSync(directory, { recursive: true, withFileTypes: true }).filter((entry) => entry.isFile())
    expect(files.length).toBeGreaterThan(0)
    for (const file of files) {
      expect(file.name.endsWith('.py')).toBe(true)
      expect(file.parentPath).toContain('app')
      expect(file.parentPath).not.toMatch(/__pycache__|\.venv|tests/)
    }
    expect(readFileSync(resolve(directory, 'app/lambda_handler.py'), 'utf8')).toContain('handler = Mangum(app')
  })

  it('rejects deployment of an incomplete Lambda asset', () => {
    expect(assertDeploymentReadiness).toThrow('NOT DEPLOYABLE')
  })

  it('rejects unexpected costly resources', () => {
    const document = foundation().template.toJSON() as { Resources: Record<string, { Type: string }> }
    document.Resources.AccidentalNat = { Type: 'AWS::EC2::NatGateway' }
    expect(() => assertFoundationSafety(document)).toThrow('Unexpected or prohibited')
  })

  it('tags all taggable foundation resources by project and stage', () => {
    const { template } = foundation()
    for (const type of ['AWS::DynamoDB::Table', 'AWS::S3::Bucket', 'AWS::Lambda::Function', 'AWS::IAM::Role', 'AWS::Logs::LogGroup']) {
      template.allResourcesProperties(type, {
        Tags: [
          { Key: 'Project', Value: 'CivicLens' },
          { Key: 'Stage', Value: 'demo' },
        ],
      })
    }
  })
})
