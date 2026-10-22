# CivicLens UI design — Phases 3–11

## Current Nearby Issues follow-up

The navy/teal workspace now exposes a labeled 1–200km slider, compact presets, explicit search
center, latest-complaint shortcut, category/status and clear/refresh actions. Same-source cards
and map markers show owner-private visibility distinctly from approved public summaries.
Local SVG category symbols use orange/red/yellow/green/blue/purple/grey; the hollow teal crosshair
sits below issue markers so a center cannot hide a co-located report. A collapsible legend and
lightweight counted clusters retain report identities and explicitly do not count unique incidents.
Search-circle metres, loading/error/empty/more-results states and mobile wrap behavior are covered
by real API and compiled-asset browser checks. [Implementation report](NEARBY_ISSUES_FIXES.md).

## Phase11 municipal operations

Existing light CivicLens typography/blue palette extends to responsive command-center cards,
chart/table alternatives, explicit filter/freshness panels, side-by-side department context,
officer workload/capacity, SLA/backlog and report previews. Never replace an API failure with demo
operational statistics. Missing data remains unavailable; unknown capacity is Not configured.
Maps distinguish report volume from canonical incidents and disclose optional external tile requests.
Wide tables scroll inside focusable labelled regions; canvases shrink without page overflow.
Desktop/mobile checks and actual screenshot evidence are recorded in PHASE_PROGRESS, not inferred.

## Phase10 UI

Existing CivicLens cards, badges, responsive grid, native Modal focus containment and error states
are reused for real inbox and administrator operations. Review-required and FAILED are distinct;
SLA OVERDUE acknowledgement is not resolution. Unknown cloud counts say Unavailable, not zero.
Citizen notification links remain owner report links; officer links require current assignment.
No private evidence, operational notes or raw event payload editor appears in inbox/monitor controls.
Browser checks use375px/1440px, Axe and horizontal-overflow assertions on isolated synthetic data.

Phase9 extends the existing responsive cards, restrained blue/slate palette, labelled forms, native
modal confirmation/focus and empty/error/loading states. ADMIN department cards use real counts;
officer cards show availability, global weighted units, explicit capacity/unknowns and labelled
utilization progress bars. Assignment pages distinguish suggested responsibility, confirmed department,
recommended officer and assigned officer. Pending priority is labelled, never rendered as zero.
Work progress remains separate from verified resolution. Officer/private notes do not appear publicly.
Cloud unavailable aggregate values are labelled unavailable rather than fabricated zero. Consequential
changes require justification, confirmation and persisted API success. Rebalancing is advisory only.

Phase8 extends existing cards/forms/badges with priority queue/statistics, unknown/verified labels,
separate calculated/effective scores, text-labelled contribution bars, hazard/override assessment
dialogs and immutable historical breakdowns. No color-only urgency meaning. Pending/stale reports
remain visible in master management and are not falsely ranked as fresh. Private notes never render
on citizen/public views. [Rubric/UI](PRIORITY_SCORING.md).

Phase7 uses existing components for ADMIN catalog/details, exact counts, bounded member/photo/history
views, tile-free private Leaflet map and confirmation/reason/version-aware corrections. Confidence
and actual membership remain separate. Citizen detail exposes only the owner's safe association.
Existing public discovery remains unchanged. Real browser375/1440px axe/overflow checks pass.
[Incident UI/workflow](INCIDENT_CLUSTERING.md).

Phase6 extends the existing light-theme cards/forms/badges without a redesign: ADMIN-only ranked
duplicate review and responsive two-column comparison collapsing to one on mobile. Scores use
similarity-index labels, never probabilities. Unavailable imagery is explicit rather than a zero;
classification/review badges, explanations, weights/version details, last-check/review times and
incomplete-state warnings remain visible. Dismiss/review/rerun controls do not merge or change
priorities. Authentication/permission/loading/API-error/empty states use existing components.
Browser verification includes375/768/1440px comparison layouts and configured axe WCAG rules.

Phase 5 extends the established visual system: full-history search/filter/date controls with URL state and server pagination; six actual statistics cards; accessible category/status bars and UTC trend lines; approved-public map/list markers with safe links; explicit owner consent and minimal ADMIN privacy review. Empty/API-error/oversized-area/denied-GPS/tile-failure states remain. Private evidence never appears on public cards. The older loaded-page-only search and sample-only discovery notes below are historical and superseded.

Phase 4 preserves the established visual system. Submit Complaint is a real guarded multipart action with a Submitting... state and persisted ID confirmation/details link; local preview is a separate non-submitting action. Failed submissions retain fields/files and retry identity. Complaint lists disclose loaded-page filtering and pagination; dashboards display actual owner counts. Private photos have authenticated loading/unavailable states. Sample mode remains visually separated and cannot submit. Title/photo limits now match the backend (10–150 characters, two 1.5-MiB images). Existing Phase 3 patterns below otherwise remain applicable.

## Identity

A light, civic-service design uses blue #2563EB for actions, #1D4ED8 for emphasis/hover, #0F172A headings, #475569/#64748B body/secondary text, #F8FAFC page surfaces and white cards. Dark blue call-to-action panels and subtle dotted/map-grid illustrations add character without paid assets, external fonts or government affiliations. Status badges use both text and semantic colors: blue submitted, amber review, violet assigned, cyan progress, emerald resolved and red rejected. Simulated data is explicitly named in banners, cards, details, notifications and map popups.

## Typography and spacing

System sans-serif with Inter as an optional installed font; no third-party font request. Headings use compact tracking and a clear h1/h2/h3 hierarchy. Body text is generally 14–16px with 1.5–1.8 line height. Page max-width is 80rem, with 16–32px responsive gutters, 16–24px card padding, 16–24px grid gaps, and larger public section spacing. Corners are 8–24px, borders slate-200, shadows subtle. Lucide icons are decorative where adjacent text supplies the meaning.

## Patterns

Primary actions use solid blue Button/action-link; secondary controls use outlined buttons. Form controls share label, border, padding and focus patterns. Errors associate descriptive text with invalid inputs; the form focuses the first invalid field. Empty views explain why there is no real data rather than making up statistics. Loading uses status text/skeletons; connection/resource errors include retry when appropriate. Dialogs use native `showModal` for focus trapping, inert backgrounds, Escape dismissal and focus restoration. Gallery files and remote failures have visible fallbacks.

## Responsive behavior

Below 1024px the citizen sidebar becomes an explicitly opened modal menu. At desktop widths the sidebar occupies 240px and the content column uses `minmax(0,1fr)`. Public navigation collapses below 768px. Forms, filters and cards grow from one to two/three/four columns based on available width. Text wraps, flex rows wrap, inputs have min-width zero, and maps are 320–420px tall. Coordinate input is always available without the map. No hover-only action, animation library, or fixed-width mobile content is used.

## Accessibility

Semantic landmarks, skip-to-content links, named navigation, visible 3px focus rings, explicit labels, described validation, text status badges, accessible icon actions and meaningful image alternatives are required. Mobile menus and modals are keyboard accessible. Reduced-motion CSS removes animations/transitions and smooth scrolling. Native controls are preferred over custom keyboard widgets. Automated browser checks use axe WCAG 2 A/AA and 2.1 AA tags; these do not replace screen-reader/user testing or certify complete WCAG compliance. Chromium viewport/keyboard verification is documented in PHASE_PROGRESS.md. Other engines and assistive technology remain future manual QA.
