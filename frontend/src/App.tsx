import { Navigate, Route, Routes } from 'react-router-dom'
import { lazy, Suspense } from 'react'
import { Skeleton } from './components/common/UI'
import { AppLayout } from './components/layout/AppLayout'
import { HomePage } from './pages/HomePage'
import { NotFoundPage } from './pages/NotFoundPage'
import { AuthProvider } from './auth/AuthProvider'
import { ProtectedRoute } from './auth/ProtectedRoute'
import { portalRoles } from './auth/types'
import { LoginPage } from './pages/LoginPage'
import { RegisterPage } from './pages/RegisterPage'
import { ForgotPasswordPage, ResetPasswordPage } from './pages/PasswordPages'
import { ProfilePage } from './pages/ProfilePage'
import { DashboardPage } from './pages/DashboardPage'
import { UnauthorizedPage } from './pages/UnauthorizedPage'
import { AuthCallbackPage } from './pages/AuthCallbackPage'
import { DashboardLayout } from './components/layout/DashboardLayout'
import { CitizenDashboard } from './pages/CitizenDashboard'
import { ReportIssuePage } from './pages/ReportIssuePage'
import { MyComplaintsPage } from './pages/MyComplaintsPage'
import { ComplaintDetailsPage } from './pages/ComplaintDetailsPage'
import { NearbyIssuesPage } from './pages/NearbyIssuesPage'
import { NotificationsPage } from './pages/NotificationsPage'
const WorkflowsPage = lazy(() =>
  import('./pages/WorkflowsPage').then((m) => ({ default: m.WorkflowsPage })),
)
import { PublicIssuePage } from './pages/PublicIssuePage'
const PublicationReviewPage = lazy(() =>
  import('./pages/PublicationReviewPage').then((m) => ({ default: m.PublicationReviewPage })),
)
const IncidentsPage = lazy(() =>
  import('./pages/IncidentsPage').then((m) => ({ default: m.IncidentsPage })),
)
const IncidentDetailsPage = lazy(() =>
  import('./pages/IncidentsPage').then((m) => ({ default: m.IncidentDetailsPage })),
)
const PrioritiesPage = lazy(() =>
  import('./pages/PrioritiesPage').then((m) => ({ default: m.PrioritiesPage })),
)
const AnalyticsPage = lazy(() =>
  import('./pages/AnalyticsPage').then((m) => ({ default: m.AnalyticsPage })),
)
const ReportsPage = lazy(() =>
  import('./pages/ReportsPage').then((m) => ({ default: m.ReportsPage })),
)
const DepartmentsPage = lazy(() =>
  import('./pages/WorkPages').then((m) => ({ default: m.DepartmentsPage })),
)
const DepartmentDetailsPage = lazy(() =>
  import('./pages/WorkPages').then((m) => ({ default: m.DepartmentDetailsPage })),
)
const AssignmentsPage = lazy(() =>
  import('./pages/WorkPages').then((m) => ({ default: m.AssignmentsPage })),
)
const AssignmentDetailsPage = lazy(() =>
  import('./pages/WorkPages').then((m) => ({ default: m.AssignmentDetailsPage })),
)
const OfficerDashboard = lazy(() =>
  import('./pages/WorkPages').then((m) => ({ default: m.OfficerDashboard })),
)
const DuplicateCandidatesPage = lazy(() =>
  import('./pages/DuplicateCandidatesPage').then((m) => ({ default: m.DuplicateCandidatesPage })),
)
const DuplicateCandidateDetailPage = lazy(() =>
  import('./pages/DuplicateCandidatesPage').then((m) => ({
    default: m.DuplicateCandidateDetailPage,
  })),
)

const RepairsPage = lazy(() =>
  import('./pages/RepairPages').then((m) => ({ default: m.RepairsPage })),
)
const OfficerRepairPage = lazy(() =>
  import('./pages/RepairPages').then((m) => ({ default: m.OfficerRepairPage })),
)
const RecurrencesPage = lazy(() =>
  import('./pages/RecurrencesPage').then((m) => ({ default: m.RecurrencesPage })),
)
const FairnessPage = lazy(() =>
  import('./pages/FairnessPage').then((m) => ({ default: m.FairnessPage })),
)

export default function App() {
  return (
    <AuthProvider>
      <Suspense fallback={<Skeleton />}>
        <Routes>
          <Route element={<AppLayout />}>
            <Route index element={<HomePage />} />
            <Route path="issues/:publicIssueId" element={<PublicIssuePage />} />
            <Route path="login" element={<LoginPage />} />
            <Route path="register" element={<RegisterPage />} />
            <Route path="forgot-password" element={<ForgotPasswordPage />} />
            <Route path="reset-password" element={<ResetPasswordPage />} />
            <Route path="auth/callback" element={<AuthCallbackPage />} />
            <Route path="unauthorized" element={<UnauthorizedPage />} />
            <Route element={<ProtectedRoute />}>
              <Route path="profile" element={<ProfilePage />} />
              <Route path="notifications" element={<NotificationsPage />} />
            </Route>
            <Route element={<ProtectedRoute roles={portalRoles.officer} />}>
              <Route path="officer/dashboard" element={<OfficerDashboard />} />
              <Route path="officer/incidents/:incidentId/repair" element={<OfficerRepairPage />} />
              <Route
                path="officer/incidents/:incidentId"
                element={<AssignmentDetailsPage officer />}
              />
            </Route>
            <Route element={<ProtectedRoute roles={portalRoles.admin} />}>
              <Route path="admin/repair-verification" element={<RepairsPage />} />
              <Route path="admin/recurrences" element={<RecurrencesPage />} />
              <Route path="admin/fairness" element={<FairnessPage />} />
              <Route path="admin/command-center" element={<AnalyticsPage />} />
              <Route path="admin/hotspots" element={<AnalyticsPage view="hotspots" />} />
              <Route path="admin/reports" element={<ReportsPage />} />
              {(
                [
                  'complaint-trends',
                  'incidents',
                  'priorities',
                  'departments',
                  'officers',
                  'sla',
                  'backlog',
                  'response-times',
                ] as const
              ).map((view) => (
                <Route
                  key={view}
                  path={`admin/analytics/${view}`}
                  element={<AnalyticsPage view={view} />}
                />
              ))}
              <Route path="admin/dashboard" element={<DashboardPage portal="admin" />} />
              <Route path="admin/workflows" element={<WorkflowsPage />} />
              <Route path="admin/workflows/:workflowId" element={<WorkflowsPage />} />
              <Route path="admin/publication-review" element={<PublicationReviewPage />} />
              <Route path="admin/incidents" element={<IncidentsPage />} />
              <Route path="admin/priorities" element={<PrioritiesPage />} />
              <Route path="admin/departments" element={<DepartmentsPage />} />
              <Route path="admin/departments/:departmentId" element={<DepartmentDetailsPage />} />
              <Route path="admin/assignments" element={<AssignmentsPage />} />
              <Route path="admin/assignments/:incidentId" element={<AssignmentDetailsPage />} />
              <Route path="admin/incidents/:incidentId" element={<IncidentDetailsPage />} />
              <Route path="admin/duplicate-candidates" element={<DuplicateCandidatesPage />} />
              <Route
                path="admin/duplicate-candidates/:candidateId"
                element={<DuplicateCandidateDetailPage />}
              />
            </Route>
            <Route path="*" element={<NotFoundPage />} />
          </Route>
          <Route element={<ProtectedRoute roles={portalRoles.citizen} />}>
            <Route path="citizen" element={<DashboardLayout />}>
              <Route index element={<Navigate to="dashboard" replace />} />
              <Route path="dashboard" element={<CitizenDashboard />} />
              <Route path="report" element={<ReportIssuePage />} />
              <Route path="complaints" element={<MyComplaintsPage />} />
              <Route path="complaints/:complaintId" element={<ComplaintDetailsPage />} />
              <Route path="nearby" element={<NearbyIssuesPage />} />
              <Route path="notifications" element={<NotificationsPage />} />
              <Route path="verification" element={<RepairsPage citizen />} />
              <Route path="profile" element={<ProfilePage />} />
            </Route>
          </Route>
        </Routes>
      </Suspense>
    </AuthProvider>
  )
}
