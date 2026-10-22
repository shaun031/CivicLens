import { describe, expect, it } from 'vitest'
import { loadEnvironment } from '../lib/config/environment.js'

describe('Stage configuration', () => {
  it('defaults to an account-agnostic demo and supports local/production', () => {
    expect(loadEnvironment()).toMatchObject({ stage: 'demo', account: undefined, region: undefined })
    expect(loadEnvironment({ stage: 'local' }).stage).toBe('local')
    expect(loadEnvironment({ stage: 'production' }).frontendOrigins).toEqual([])
  })
  it('parses exact JSON origins and optional account/region without lookups', () => {
    expect(loadEnvironment({ stage: 'production', frontendOrigins: '["https://civic.example.org"]', account: '123456789012', region: 'ap-south-1' })).toMatchObject({
      frontendOrigins: ['https://civic.example.org'], account: '123456789012', region: 'ap-south-1',
    })
  })
  it.each([
    { stage: 'unknown' }, { frontendOrigins: '*' }, { frontendOrigins: ['*'] },
    { frontendOrigins: ['https://civic.example.org/path'] }, { frontendOrigins: ['https://*.example.org'] },
    { stage: 'production', frontendOrigins: ['http://civic.example.org'] },
    { stage: 'production', frontendOrigins: ['https://localhost'] },
    { frontendOrigins: [123] }, { account: '1234' }, { region: 'invalid' },
  ])('rejects unsafe or malformed configuration %j', (input) => {
    expect(() => loadEnvironment(input)).toThrow()
  })
})
