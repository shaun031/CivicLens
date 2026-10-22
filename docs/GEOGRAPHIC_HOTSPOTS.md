# Private geographic concentrations

ADMIN `/admin/hotspots` uses the same validated filters and a spatial-grid overlay. Grid size is
0.001–0.1 degrees, not a fixed number of metres; longitudinal ground distances vary with latitude.
The initial example viewport is not a configured municipality or evidence of local incidents.
Enter service-area bounds or pan/zoom and explicitly apply the viewport. Requests are not polled.

Non-wrapping latitude/longitude bounds are mandatory, at most2 degrees per axis and10000 possible
cells; at most2000 occupied cells are returned. Invalid/infinite/incomplete coordinates are rejected.
The map renders the first500 occupied cells with an explicit visual limit, while the accessible
cell list contains the complete bounded response. The optional OSM basemap is off by default and
requires opt-in because tile requests reveal map interest to an external server. No paid geocoder.

Cell indices use decimal floor(latitude/grid), floor(longitude/grid). Global positive endpoints
are clamped into the last non-degenerate cell. Each canonical incident contributes to one cell
using its representative coordinate. Each eligible report contributes independently using its
report coordinate; unlinked/report-only cells can exist. These are different measures and cohorts.

Cell metrics: incident count, active count, current critical count, distinct current overdue count,
report volume, and mean fresh calculated score plus sample size. Missing scores remain null.
Merges/splits use current canonical records; aliases never add active defects. Intensity can select
canonical incidents, report volume, critical incidents or overdue incidents. Values and legend text
remain available without relying only on colour. No reporter identifiers, notes or photographs
are included. CSV exports contain grid IDs/aggregate counts, not exact private report coordinates.

This describes concentrations of observed reports/incidents, not exhaustive infrastructure defects,
population-adjusted risk, causation or geographic fairness. Small cells can reveal a single known
incident; this API is private ADMIN-only and must not be reused for a public map. Public sharing
would need separate thresholds, coarsening and privacy review. No Phase12 fairness engine is added.
