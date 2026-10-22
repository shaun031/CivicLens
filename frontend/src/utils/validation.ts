import type { ComplaintDraft } from '../types/complaint'
import { categories } from '../types/complaint'
export const MAX_FILES = 2
export const MAX_FILE_SIZE = 1.5 * 1024 * 1024
export const imageTypes = ['image/jpeg', 'image/png', 'image/webp']
export function validateFiles(files: File[]): string | undefined {
  if (files.length > MAX_FILES) return 'Choose no more than 2 images.'
  if (files.some((file) => !imageTypes.includes(file.type)))
    return 'Only JPEG, PNG, and WebP images are supported.'
  if (files.some((file) => file.size === 0 || file.size > MAX_FILE_SIZE))
    return 'Each image must be non-empty and no larger than 1.5 MiB.'
}
export function validCoordinates(latitude: string, longitude: string) {
  return (
    latitude.trim() !== '' &&
    longitude.trim() !== '' &&
    Number.isFinite(Number(latitude)) &&
    Number.isFinite(Number(longitude)) &&
    Math.abs(Number(latitude)) <= 90 &&
    Math.abs(Number(longitude)) <= 180
  )
}
export function validateDraft(draft: ComplaintDraft) {
  const errors: Partial<Record<keyof ComplaintDraft, string>> = {}
  if (!Object.hasOwn(categories, draft.category)) errors.category = 'Choose a complaint category.'
  if (draft.title.trim().length < 10 || draft.title.length > 150)
    errors.title = 'Use a title between 10 and 150 characters.'
  if (draft.description.trim().length < 20 || draft.description.length > 2000)
    errors.description = 'Describe the issue in 20 to 2,000 characters.'
  if (draft.addressLabel.length > 200)
    errors.addressLabel = 'Use no more than 200 characters for the address.'
  if (draft.landmark.length > 200)
    errors.landmark = 'Use no more than 200 characters for the landmark.'
  if (!validCoordinates(draft.latitude, draft.longitude))
    errors.latitude = 'Enter latitude from −90 to 90 and longitude from −180 to 180.'
  if (!['LOW', 'MEDIUM', 'HIGH'].includes(draft.reportedSeverity))
    errors.reportedSeverity = 'Choose a severity.'
  errors.files = validateFiles(draft.files)
  return Object.fromEntries(Object.entries(errors).filter(([, value]) => value)) as typeof errors
}
