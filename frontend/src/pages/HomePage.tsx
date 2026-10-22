import {
  ArrowRight,
  MapPin,
  ShieldCheck,
  Route,
  Camera,
  Check,
  Layers,
  CircleDot,
} from 'lucide-react'
import { Link } from 'react-router-dom'
const features = [
  {
    Icon: MapPin,
    title: 'Put the issue on the map',
    detail:
      'Pin a location, describe the problem, and attach a photograph. A clear report makes the next step easier.',
  },
  {
    Icon: Layers,
    title: 'Connect the bigger picture',
    detail: 'Related reports help reviewers understand shared incidents and assess their priority.',
  },
  {
    Icon: ShieldCheck,
    title: 'Follow through with confidence',
    detail:
      'See recorded updates and take part in repair verification when your report is eligible.',
  },
]
export function HomePage() {
  return (
    <>
      <section className="landing-hero">
        <div className="landing-copy">
          <p className="landing-kicker">
            <span />
            Your neighborhood. Your perspective.
          </p>
          <h1>
            Smarter reporting.
            <br />
            <span>Better places</span>
            <br />
            to call home.
          </h1>
          <p className="landing-lead">
            From the pothole on your street to the light that needs fixing. Report infrastructure
            problems and follow their progress, all in one place.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link className="action-link" to="/citizen/report">
              Report an Issue <ArrowRight size={17} aria-hidden="true" />
            </Link>
            <Link className="secondary-button" to="/citizen/nearby">
              Explore Public Issues <MapPin size={16} aria-hidden="true" />
            </Link>
          </div>
          <p className="landing-assurance">
            <ShieldCheck size={15} aria-hidden="true" />
            Private reports. Reviewed public summaries.
          </p>
        </div>
        <div className="neighborhood-visual">
          <div className="visual-toolbar">
            <span>
              <span className="visual-dot" />A connected neighborhood
            </span>
            <MapPin size={16} aria-hidden="true" />
          </div>
          <svg
            viewBox="0 0 520 440"
            role="img"
            aria-label="Illustrative neighborhood map, not live reports"
            className="neighborhood-map"
          >
            <defs>
              <pattern id="map-grid" width="32" height="32" patternUnits="userSpaceOnUse">
                <path d="M32 0H0V32" fill="none" stroke="#e2e8f0" strokeWidth=".7" />
              </pattern>
            </defs>
            <rect width="520" height="440" fill="#f1f5f4" />
            <rect width="520" height="440" fill="url(#map-grid)" />
            <rect x="32" y="36" width="125" height="105" rx="16" fill="#dce9e1" />
            <rect x="339" y="265" width="150" height="132" rx="18" fill="#dce9e1" />
            <path
              d="M404-20C314 90 420 147 377 236S394 370 322 460"
              fill="none"
              stroke="#c5dee0"
              strokeWidth="37"
            />
            <path
              d="M-30 248L550 111M190-20L240 470M-10 355L540 328M-10 170L294 451"
              fill="none"
              stroke="#e2e8e8"
              strokeWidth="31"
            />
            <path
              d="M-30 248L550 111M190-20L240 470M-10 355L540 328M-10 170L294 451"
              fill="none"
              stroke="white"
              strokeWidth="24"
            />
            {[
              [55, 172, 75, 28],
              [260, 46, 72, 48],
              [266, 214, 66, 65],
              [49, 273, 79, 36],
              [271, 356, 40, 47],
              [437, 181, 50, 48],
            ].map(([x, y, w, h]) => (
              <rect key={x + y} x={x} y={y} width={w} height={h} rx="6" fill="#d6dfdf" />
            ))}
            {[
              [78, 76],
              [107, 97],
              [392, 304],
              [438, 328],
              [420, 364],
            ].map(([x, y]) => (
              <g key={x}>
                <circle cx={x} cy={y} r="14" fill="#b9d3c3" />
                <circle cx={x - 3} cy={y - 3} r="9" fill="#c6ddcc" />
              </g>
            ))}
            <path
              d="M134 226L221 205L230 336L295 333"
              stroke="#0d9488"
              strokeWidth="3"
              strokeDasharray="6 6"
              fill="none"
            />
            {[
              [134, 226],
              [295, 333],
              [306, 169],
            ].map(([x, y], i) => (
              <g key={x}>
                <circle cx={x} cy={y} r="24" fill="#0d9488" opacity=".09" />
                <circle
                  cx={x}
                  cy={y}
                  r="13"
                  fill={i === 1 ? '#0f172a' : '#0f766e'}
                  stroke="white"
                  strokeWidth="3"
                />
                <circle cx={x} cy={y} r="3" fill="white" />
              </g>
            ))}
          </svg>
          <div className="visual-report">
            <span className="visual-report-icon">
              <Route size={20} aria-hidden="true" />
            </span>
            <div>
              <strong>A clearer path to action</strong>
              <p>Report. Review. Repair.</p>
            </div>
            <span className="visual-check">
              <Check size={16} aria-hidden="true" />
            </span>
          </div>
          <p className="visual-caption">Neighborhood illustration · Not live operational data</p>
        </div>
      </section>
      <section className="landing-features" aria-labelledby="features-title">
        <div className="landing-section-heading">
          <div>
            <p className="eyebrow">Designed around your community</p>
            <h2 id="features-title">
              Less friction.
              <br />
              More follow-through.
            </h2>
          </div>
          <p>
            A simple way to turn an everyday observation into a report that can be reviewed,
            tracked, and acted on.
          </p>
        </div>
        <div className="feature-grid">
          {features.map(({ Icon, title, detail }, i) => (
            <article key={title}>
              <div className="feature-number">
                0{i + 1}
                <Icon size={24} strokeWidth={1.6} aria-hidden="true" />
              </div>
              <h3>{title}</h3>
              <p>{detail}</p>
            </article>
          ))}
        </div>
      </section>
      <section className="landing-process" aria-labelledby="how-title">
        <div>
          <p className="eyebrow">A few minutes to make a difference</p>
          <h2 id="how-title">
            Notice it. Report it.
            <br />
            Stay in the loop.
          </h2>
          <Link className="action-link mt-7" to="/register">
            Create your account <ArrowRight size={16} aria-hidden="true" />
          </Link>
        </div>
        <ol>
          {[
            [
              Camera,
              'Describe what you see',
              'Choose a category and add context with optional photographic evidence.',
            ],
            [
              MapPin,
              'Choose the right location',
              'Drop a pin or enter coordinates so the issue is easy to find.',
            ],
            [
              CircleDot,
              'Track recorded progress',
              'Follow your complaint and review updates in your private workspace.',
            ],
          ].map(([Icon, title, detail], i) => {
            const StepIcon = Icon as typeof Camera
            return (
              <li key={String(title)}>
                <span>
                  <StepIcon size={21} aria-hidden="true" />
                </span>
                <div>
                  <p className="process-label">STEP 0{i + 1}</p>
                  <h3>{String(title)}</h3>
                  <p>{String(detail)}</p>
                </div>
              </li>
            )
          })}
        </ol>
      </section>
    </>
  )
}
