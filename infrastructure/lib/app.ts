import { App, DefaultStackSynthesizer, type AppProps } from 'aws-cdk-lib'
import { loadEnvironment } from './config/environment.js'
import { CivicLensStack } from './stacks/civiclens-stack.js'

export function createCdkApp(props: AppProps = {}): App {
  const app = new App(props)
  const config = loadEnvironment({
    stage: app.node.tryGetContext('stage'),
    frontendOrigins: app.node.tryGetContext('frontendOrigins'),
    account: app.node.tryGetContext('account'),
    region: app.node.tryGetContext('region'),
    callbackUrls: app.node.tryGetContext('callbackUrls'),
    logoutUrls: app.node.tryGetContext('logoutUrls'),
  })
  if (config.stage !== 'local') {
    new CivicLensStack(app, `CivicLens-${config.stage}`, {
      config: { ...config, stage: config.stage },
      env: { account: config.account, region: config.region },
      description: `CivicLens ${config.stage} Phase 2 infrastructure definitions — deployment blocked`,
      analyticsReporting: false,
      // Stages file assets locally without bootstrap-version lookups or credentials.
      synthesizer: new DefaultStackSynthesizer({ generateBootstrapVersionRule: false }),
    })
  }
  return app
}
