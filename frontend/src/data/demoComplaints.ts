import type { Category, Complaint, ComplaintStatus } from '../types/complaint'

// Fictional reports at illustrative Bengaluru coordinates. Never tied to an authenticated citizen.
const examples: { title: string; category: Category; status: ComplaintStatus; label: string }[] = [
  {
    title: 'Pothole beside the community library',
    category: 'POTHOLE',
    status: 'SUBMITTED',
    label: 'Sample Library Road',
  },
  {
    title: 'Uneven surface on the cycle lane',
    category: 'DAMAGED_ROAD',
    status: 'UNDER_REVIEW',
    label: 'Sample Park Avenue',
  },
  {
    title: 'Streetlight not working near the crossing',
    category: 'BROKEN_STREETLIGHT',
    status: 'ASSIGNED',
    label: 'Sample Market Crossing',
  },
  {
    title: 'Waste collecting beside the park',
    category: 'GARBAGE',
    status: 'IN_PROGRESS',
    label: 'Sample Garden Lane',
  },
  {
    title: 'Blocked drain on a residential street',
    category: 'DRAINAGE',
    status: 'RESOLVED',
    label: 'Sample Lake Street',
  },
  {
    title: 'Damaged bench at the bus shelter',
    category: 'PUBLIC_PROPERTY_DAMAGE',
    status: 'REJECTED',
    label: 'Sample Central Stop',
  },
]
const stages: ComplaintStatus[] = [
  'SUBMITTED',
  'UNDER_REVIEW',
  'ASSIGNED',
  'IN_PROGRESS',
  'RESOLVED',
]
export const demoComplaints: Complaint[] = examples.map((item, index) => {
  const createdAt = `2026-10-${String(10 + index).padStart(2, '0')}T08:00:00.000Z`
  const progress = (
    item.status === 'REJECTED'
      ? (['SUBMITTED', 'UNDER_REVIEW', 'REJECTED'] as ComplaintStatus[])
      : stages.slice(0, stages.indexOf(item.status) + 1)
  ).map((status, step) => ({
    status,
    createdAt: createdAt.replace('08:00', `${String(8 + step).padStart(2, '0')}:00`),
    message: 'Simulated progress event for interface demonstration.',
  }))
  return {
    ...item,
    complaintId: `sample-${index + 1}`,
    citizenId: 'fictional-demo-citizen',
    incidentId: index === 3 ? 'sample-incident-1' : undefined,
    description:
      'Fictional infrastructure issue created to demonstrate CivicLens. This is not a report from a real resident and no department has been contacted.',
    location: {
      latitude: 12.9716 + index * 0.004,
      longitude: 77.5946 + index * 0.003,
      addressLabel: item.label,
    },
    imageKeys: [],
    images:
      index === 0
        ? [
            {
              url: '/images/sample-road.svg',
              alt: 'Illustration of a road defect — sample evidence, not a real photograph',
            },
          ]
        : [],
    reportedSeverity: index % 2 === 0 ? 'HIGH' : 'MEDIUM',
    createdAt,
    updatedAt: progress.at(-1)!.createdAt,
    progress,
    isSimulated: true,
  }
})
