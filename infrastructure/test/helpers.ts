import { Template } from 'aws-cdk-lib/assertions'
import { createCdkApp } from '../lib/app.js'
import type { CloudStage } from '../lib/config/environment.js'
import type { CivicLensStack } from '../lib/stacks/civiclens-stack.js'

export function foundation(stage: CloudStage = 'demo', frontendOrigins?: string[]) {
  const app = createCdkApp({ context: { stage, ...(frontendOrigins ? { frontendOrigins } : {}) } })
  const stack = app.node.findChild(`CivicLens-${stage}`) as CivicLensStack
  // Keep synthesis lazy so permission tests can add a future grantee first.
  return { app, stack, get template() { return Template.fromStack(stack) } }
}
