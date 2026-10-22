import type { Complaint } from '../types/complaint'
export interface FilterValues {
  search: string
  category: string
  status: string
  sort: string
  severity?: string
  dateFrom?: string
  dateTo?: string
}
export const emptyFilters: FilterValues = {
  search: '',
  category: '',
  status: '',
  sort: 'newest',
  severity: '',
  dateFrom: '',
  dateTo: '',
}
export function filterComplaints(items: Complaint[], filters: FilterValues) {
  return items
    .filter(
      (item) =>
        (!filters.category || item.category === filters.category) &&
        (!filters.status || item.status === filters.status) &&
        (!filters.severity || item.reportedSeverity === filters.severity) &&
        (!filters.dateFrom || item.createdAt.slice(0, 10) >= filters.dateFrom) &&
        (!filters.dateTo || item.createdAt.slice(0, 10) <= filters.dateTo) &&
        `${item.title} ${item.description} ${item.location.addressLabel}`
          .toLowerCase()
          .includes(filters.search.trim().toLowerCase()),
    )
    .sort((a, b) => {
      const primary =
        filters.sort === 'category'
          ? a.category.localeCompare(b.category)
          : filters.sort === 'status'
            ? a.status.localeCompare(b.status)
            : 0
      return (
        primary ||
        (filters.sort === 'newest' ? -1 : 1) *
          (a.createdAt.localeCompare(b.createdAt) || a.complaintId.localeCompare(b.complaintId))
      )
    })
}
