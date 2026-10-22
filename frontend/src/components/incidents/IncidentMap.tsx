import { divIcon } from 'leaflet'
import { MapContainer, Marker, Popup, Tooltip } from 'react-leaflet'
import type { Incident, IncidentMember } from '../../services/incidentService'
import { MapResize } from '../maps/MapSupport'

const master = divIcon({
  className: 'civic-map-marker',
  html: '<span aria-hidden="true">I</span>',
  iconSize: [28, 28],
})
const report = divIcon({
  className: 'civic-map-marker selected',
  html: '<span aria-hidden="true">R</span>',
  iconSize: [24, 24],
})
export default function IncidentMap({
  incident,
  members,
}: {
  incident: Incident
  members: IncidentMember[]
}) {
  return (
    <section aria-label="Private administrator incident map" className="space-y-3">
      <p className="text-sm">
        Private map. I = representative incident; R = linked report. Distances are relative to the
        incident. No external basemap is loaded.
      </p>
      <MapContainer
        key={`${incident.incidentId}:${incident.version}`}
        center={[incident.latitude, incident.longitude]}
        zoom={18}
        scrollWheelZoom={false}
        className="h-80 w-full rounded-xl bg-slate-100"
      >
        <MapResize />
        <Marker
          position={[incident.latitude, incident.longitude]}
          icon={master}
          title="Master incident"
          alt="Master incident"
        >
          <Popup>
            <strong>Master incident</strong>
            <p>{incident.canonicalTitle}</p>
          </Popup>
          <Tooltip permanent direction="top" offset={[0, -15]}>
            Incident representative
          </Tooltip>
        </Marker>
        {members.slice(0, 30).map((member) => (
          <Marker
            key={member.complaintId}
            position={[member.latitude, member.longitude]}
            icon={report}
            title={member.title}
            alt={`Linked report: ${member.title}`}
          >
            <Popup>
              <strong>{member.title}</strong>
              <p>
                {member.distanceMeters?.toFixed(1) ?? 'Distance unavailable'} m from representative
              </p>
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </section>
  )
}
