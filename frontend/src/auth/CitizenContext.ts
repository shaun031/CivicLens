import { createContext, useContext } from 'react'
import type { Dispatch, SetStateAction } from 'react'
import type { ComplaintDraft } from '../types/complaint'
import type { NearbySearch } from '../types/nearby'
export interface CitizenState {
  demo: boolean
  setDemo: Dispatch<SetStateAction<boolean>>
  draft: ComplaintDraft
  setDraft: Dispatch<SetStateAction<ComplaintDraft>>
  readNotifications: string[]
  setReadNotifications: Dispatch<SetStateAction<string[]>>
  nearbySearch: NearbySearch
  setNearbySearch: Dispatch<SetStateAction<NearbySearch>>
}
export const CitizenContext = createContext<CitizenState | null>(null)
export function useCitizen() {
  const value = useContext(CitizenContext)
  if (!value) throw new Error('Citizen workspace is missing')
  return value
}
