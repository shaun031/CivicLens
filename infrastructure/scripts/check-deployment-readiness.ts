import { assertDeploymentReadiness } from '../lib/safety.js'

try {
  assertDeploymentReadiness()
} catch (error: unknown) {
  console.error(error instanceof Error ? error.message : error)
  process.exitCode = 1
}
