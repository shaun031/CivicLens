import { createCdkApp } from '../lib/app.js'

// The CDK CLI exits nonzero for an empty app; check the local stage directly.
const assembly = createCdkApp({ context: { stage: 'local' }, outdir: 'cdk.out/local' }).synth()
if (assembly.stacks.length !== 0) throw new Error('Local stage must not contain cloud stacks')
console.log('Local stage verified: zero cloud stacks and zero AWS resources defined.')
