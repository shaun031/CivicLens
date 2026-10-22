# CivicLens frontend design system

Phase 14 introduces a local frontend redesign. Existing FastAPI contracts, role checks, evidence authorization and SQLite records remain authoritative. No cloud deployment is part of this phase.

## Foundations

| Token | Value | Use |
|---|---|---|
| `--ink`, `--navy` | `#0F172A` | Text, brand, focused dark panels |
| `--accent` | `#0D9488` | Icons, highlights, selected indicators |
| `--action` | `#0F766E` | Small text links and white-text buttons (stronger contrast) |
| `--action-hover` | `#115E59` | Hover feedback |
| `--canvas` | `#F8FAFC` | Application background |
| `--surface` | `#FFFFFF` | Cards, sidebar and forms |
| `--muted` | `#64748B` | Supporting text |
| `--line` | `#E2E8F0` | Borders and separators |
| `--success` | `#16A34A` | Successful states |
| `--warning` | `#F59E0B` | Caution and medium priorities |
| `--error` | `#DC2626` | Errors, critical/high priority |

Inter is the first font preference; system UI / Segoe UI provide a local fallback without an external font request. Heading scale is responsive (roughly 26–34px for app pages); forms/body use 14px and supporting metadata a smaller scale. No remote fonts, paid services, icon packs or animation libraries were added.

Spacing follows Tailwind's existing 4px scale, with 16/24px card/grid gaps and responsive `--space-page`. Shared cards use a 16px radius, subtle border/shadow and readable white surfaces. Utility classes remain useful for contextual layout; reusable primitives own the common visual rules in `src/styles/index.css`.

## Components and layout

- `Brand`: shared wordmark and Lucide symbol, with compact/light variants.
- `AppShell`: reusable desktop sidebar, topbar, account disclosure, mobile drawer, skip link, content and compact footer. The sidebar can collapse without removing navigation.
- `Sidebar`: role-specific links; administrator groups separate teams/operations, review/quality and analytics/maps. Every original route remains in `App.tsx`.
- `PageHeader`, `Card`, `Button`, `Badge`, `PriorityBadge`, `Skeleton`, `ErrorState`, `EmptyState`, `Field`, `Select`, `Textarea`, `PasswordField`, `FormMessage` and native `Modal` provide consistent interactions.
- `StatCard`, `ComplaintCard`, `CategoryIcon`, recorded `ComplaintTimeline`, `AnalyticsTable`, lazy `Chart` and `ImageUpload` reuse existing domain types and services.
- `DashboardLayout` retains the in-memory citizen draft/sample-preview context and backend portal verification. It delegates visual layout to `AppShell`.
- `AuthCard` provides a split desktop layout and compact mobile form. Profile editing uses the workspace layout, not an authentication story panel.

Citizen navigation retains Dashboard, Report Issue, My Complaints, Nearby Issues, Repair Verification, Notifications and Profile. Officer navigation retains assigned-work access and links to progress/repair actions inside authorized incident detail. Administrator merge/split, recurrence, fairness, publication, priority, allocation, workflow and report tools retain their own routes and permissions.

## Content and data

Landing-page map artwork is explicitly labeled as an illustration; no operational statistics or partnerships are fabricated. Citizen statistics use the existing summary API. Charts and secondary status counts are available through Reporting insights. Sample mode stays explicit and opt-in; it cannot submit real reports or verification responses.

Only recorded complaint milestones appear in the timeline. Cards omit repeated severity/evidence previews; complete fields and photographs remain on detail pages. Administrator overview puts four core metrics and three charts first, retaining extra charts/counts behind a disclosure. Source-window/freshness details remain available. Officer summary values come from the existing queue; the awaiting-review count is explicitly labeled as the current filtered page, not a global repair total.

Image drop and file selection share the same existing size/type validator. Images are selected locally and are only uploaded by the existing submission request. Empty states and request failures never substitute demonstration data. Existing cursor pagination, search debounce and stale-response guards remain in place.

## Motion

Native CSS transitions/keyframes use `--duration: 200ms` and `--ease`, without an extra JavaScript bundle. Page/card entrances, sidebar width/drawer, account disclosures, modal appearance, buttons, report section focus, skeletons, feedback messages, map/list panels and expandable content have restrained feedback. No row-by-row or continuous decorative animation is used. Skeleton motion is limited to loading content.

Native disclosures animate their entering content; closed controls retain native hidden behavior. Experimental content-visibility/height interpolation was removed after a browser-scanner compatibility failure. `prefers-reduced-motion: reduce` disables animations, transitions and smooth scrolling. Chart animation remains disabled for responsiveness and stable data reading.

## Accessibility

Use one page h1, meaningful sections, labeled controls and visible keyboard focus. Buttons keep text or accessible icon labels. Status/priority badges include words, not just color. Native modal dialogs retain focus containment, inert background, Escape and focus restoration. Account dropdowns close on Escape and outside click. Scrollable table regions retain accessible captions and keyboard focus. Charts expose data tables; map coordinates/list views remain alternatives to pointer map interaction.

The contrast target is WCAG AA; teal-700 is used for small foreground actions and white-text buttons. WCAG 2.2 AA automated checks and representative keyboard journeys are in `e2e/redesign.spec.ts`. Automated checks do not constitute a complete human accessibility audit.

## Responsive behavior

- Under 768px: single-column auth, dashboards/forms, compact user controls, wrapping actions and cards.
- Under 1024px: navigation uses an accessible modal drawer.
- 1024px and above: persistent sidebar and collapsible compact mode.
- 1280px and above: four primary metrics and three main operational charts where space permits.

Tables scroll inside their own labeled region, not the entire page. Modal width/height respect the viewport. Representative verification widths: 375, 768, 1024 and 1440px. Screenshots and actual verification results are recorded in `PHASE14_IMPLEMENTATION_REPORT.md`.
