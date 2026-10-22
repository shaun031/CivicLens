import { describe, expect, it, vi } from 'vitest'
import { emptyDraft } from '../types/complaint'
import { validateDraft, validateFiles, validCoordinates, MAX_FILE_SIZE } from '../utils/validation'
import { complaintService } from '../services/complaintService'
import { notificationService } from '../services/notificationService'
import { demoComplaints } from '../data/demoComplaints'
import { emptyFilters, filterComplaints } from '../utils/complaints'
import { formatDate } from '../utils/dates'
describe('Phase 3 typed data boundaries', () => {
  it('keeps unavailable discovery/notifications and explicit samples separate from real HTTP', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch')
    expect((await complaintService.list(true)).items).toHaveLength(6)
    expect(await complaintService.nearby(false)).toEqual([])
    expect(await complaintService.detail('sample-1', false)).toBeNull()
    expect((await notificationService.list(true)).every((item) => item.isSimulated)).toBe(true)
    expect(fetch).not.toHaveBeenCalled()
    fetch.mockRestore()
  })
  it('returns isolated fixture copies, with fictional citizen IDs and real progress subsets', async () => {
    const first = (await complaintService.list(true)).items
    first[0].title = 'Changed locally'
    expect((await complaintService.list(true)).items[0].title).not.toBe('Changed locally')
    expect(
      first.every((item) => item.isSimulated && item.citizenId === 'fictional-demo-citizen'),
    ).toBe(true)
    expect(first[0].progress.map((event) => event.status)).toEqual(['SUBMITTED'])
    expect(await complaintService.detail('unknown', true)).toBeNull()
  })
  it.each([
    ['', '77'],
    ['90.1', '0'],
    ['0', '-180.1'],
    ['NaN', '0'],
    ['1e999', '0'],
    ['0', '   '],
  ])('rejects invalid coordinates %s, %s', (lat, lng) =>
    expect(validCoordinates(lat, lng)).toBe(false),
  )
  it.each([
    ['-90', '180'],
    ['90', '-180'],
    ['0', '0'],
    ['12.97', '77.59'],
  ])('accepts valid coordinates %s, %s', (lat, lng) =>
    expect(validCoordinates(lat, lng)).toBe(true),
  )
  it('validates text limits and required category without prototype-key bypasses', () => {
    expect(Object.keys(validateDraft(emptyDraft()))).toContain('category')
    const invalid = {
      ...emptyDraft(),
      category: 'toString',
      title: 'x'.repeat(151),
      description: 'x'.repeat(2001),
      addressLabel: 'x'.repeat(201),
    }
    const errors = validateDraft(invalid as ReturnType<typeof emptyDraft>)
    expect(errors).toHaveProperty('category')
    expect(errors).toHaveProperty('title')
    expect(errors).toHaveProperty('description')
    expect(errors).toHaveProperty('addressLabel')
  })
  it('enforces file count, exact size limit, zero bytes and MIME allowlist', () => {
    const png = new File(['a'], 'a.png', { type: 'image/png' })
    expect(validateFiles([png, png, png])).toMatch('2 images')
    expect(validateFiles([new File([], 'empty.png', { type: 'image/png' })])).toMatch('non-empty')
    Object.defineProperty(png, 'size', { value: MAX_FILE_SIZE })
    expect(validateFiles([png])).toBeUndefined()
    expect(validateFiles([new File(['x'], 'fake.png', { type: 'text/html' })])).toMatch('Only JPEG')
  })
  it('sorts without mutating fixtures, combines filters, and handles empty results', () => {
    expect(filterComplaints(demoComplaints, emptyFilters)[0].complaintId).toBe('sample-6')
    expect(demoComplaints[0].complaintId).toBe('sample-1')
    expect(
      filterComplaints(demoComplaints, {
        ...emptyFilters,
        category: 'POTHOLE',
        status: 'SUBMITTED',
        search: 'LIBRARY',
      }),
    ).toHaveLength(1)
    expect(filterComplaints(demoComplaints, { ...emptyFilters, search: 'not present' })).toEqual([])
  })
  it('formats missing dates safely', () => expect(formatDate('invalid')).toBe('Date unavailable'))
})
