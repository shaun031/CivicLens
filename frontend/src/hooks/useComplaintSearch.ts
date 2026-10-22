import { useCallback } from 'react'
import { complaintService } from '../services/complaintService'
import type { FilterValues } from '../utils/complaints'
import { useResource } from './useResource'

export function useComplaintSearch(
  demo: boolean,
  { search, category, status, severity, dateFrom, dateTo, sort }: Readonly<FilterValues>,
) {
  const loader = useCallback(
    () =>
      complaintService.list(demo, undefined, {
        search,
        category,
        status,
        severity,
        dateFrom,
        dateTo,
        sort,
      }),
    [demo, search, category, status, severity, dateFrom, dateTo, sort],
  )
  return useResource(loader)
}
