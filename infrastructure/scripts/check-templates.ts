import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { assertFoundationSafety, type FoundationTemplate } from '../lib/safety.js'

const directory = resolve(process.argv[2] ?? 'cdk.out')
// Read only stacks in the current assembly; older synth files may remain on disk.
const manifest = JSON.parse(readFileSync(resolve(directory, 'manifest.json'), 'utf8')) as {
  artifacts: Record<string, { type: string; properties?: { templateFile?: string } }>
}
const files = Object.values(manifest.artifacts)
  .filter((artifact) => artifact.type === 'aws:cloudformation:stack')
  .map((artifact) => artifact.properties?.templateFile)
if (files.some((file) => !file)) throw new Error('Stack manifest has no template file')
if (files.length !== 1) throw new Error(`Expected one cloud stack template in ${directory}, found ${files.length}`)
for (const file of files) {
  const template = JSON.parse(readFileSync(resolve(directory, file!), 'utf8')) as FoundationTemplate
  assertFoundationSafety(template)
  console.log(`${file}: expected resources, JWT-protected routes, scoped IAM, and deployment block verified locally.`)
}
