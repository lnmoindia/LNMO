import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import "./App.css";
import { Toaster } from "./components/ui/sonner";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { ThemeProvider } from "./context/ThemeContext";
import { ReportIssueProvider } from "./context/ReportIssue";
import PlatformIssues from "./pages/platform/PlatformIssues";
import SupportPage from "./pages/institution/SupportPage";
import CrashTest from "./pages/institution/CrashTest";
import { platformNav } from "./navigation";
import AppShell from "./components/layout/AppShell";
import ResourcePage from "./components/common/ResourcePage";
import LoginPage, { roleHome } from "./pages/LoginPage";
import PlatformDashboard from "./pages/platform/PlatformDashboard";
import PlatformInstitutionsPage from "./pages/platform/PlatformInstitutionsPage";
import InstitutionDetail from "./pages/platform/InstitutionDetail";
import InstitutionDashboard from "./pages/institution/InstitutionDashboard";
import InstitutionLayout from "./pages/institution/InstitutionLayout";
import SetupWizard from "./pages/institution/SetupWizard";
import ClassHub from "./pages/institution/ClassHub";
import ClassDetailPage from "./pages/institution/ClassDetailPage";
import SectionDetailPage from "./pages/institution/SectionDetailPage";
import TimetablePage from "./pages/institution/timetable/TimetablePage";
import SubstitutionsPage from "./pages/institution/SubstitutionsPage";
import NotificationsPage from "./pages/NotificationsPage";
import StudentsPage from "./pages/institution/StudentsPage";
import SubjectImportButton from "./pages/institution/SubjectImportDialog";
import StudentPortal from "./pages/student/StudentPortal";
import TeachersPage from "./pages/institution/TeachersPage";
import TeacherProfileView from "./pages/institution/TeacherProfileView";
import HomeworkMonitor from "./pages/institution/HomeworkMonitor";
import PlatformCommunication from "./pages/platform/PlatformCommunication";
import PlatformLibrary from "./pages/platform/PlatformLibrary";
import PlatformSettings from "./pages/platform/PlatformSettings";
import ResetPasswordPage from "./pages/ResetPasswordPage";
import CommunicationPage from "./pages/institution/CommunicationPage";
import StudentProfileView from "./pages/institution/StudentProfileView";
import UsersPage from "./pages/institution/UsersPage";
import ChangePasswordPage from "./pages/institution/ChangePasswordPage";
import ParentSetupPage from "./pages/ParentSetupPage";
import FeeLinkPage from "./pages/FeeLinkPage";
import AuditPage from "./pages/AuditPage";
import InstitutionSettingsPage from "./pages/InstitutionSettingsPage";
import { AccessDeniedPage, NotFoundPage, ComingSoonPage } from "./pages/StatusPages";
import TeacherShell from "./components/layout/TeacherShell";
import PrincipalsPage from "./pages/institution/PrincipalsPage";
import PrincipalDashboard from "./pages/principal/PrincipalDashboard";
import { AdminOnly, AdminOrPrincipal } from "./components/common/RoleGuards";
import AttendancePage from "./pages/AttendancePage";
import MarksEntryPage from "./pages/MarksEntryPage";
import AssessmentsPage from "./pages/institution/AssessmentsPage";
import ExamsPage from "./pages/institution/exams/ExamsPage";
import ExamDetailPage from "./pages/institution/exams/ExamDetailPage";
import TeacherDashboard from "./pages/teacher/TeacherDashboard";
import TeacherStudents from "./pages/teacher/TeacherStudents";
import TeacherTimetable from "./pages/teacher/TeacherTimetable";
import TeacherSubstitutions from "./pages/teacher/TeacherSubstitutions";
import TeacherMyClass from "./pages/teacher/TeacherMyClass";
import TeacherMarksList from "./pages/teacher/TeacherMarksList";
import TeacherProfile from "./pages/teacher/TeacherProfile";
import TeacherHomework from "./pages/teacher/TeacherHomework";
import TeacherAssignments from "./pages/teacher/TeacherAssignments";
import TeacherFeeDefaulters from "./pages/teacher/TeacherFeeDefaulters";
import NoticesPage from "./pages/institution/NoticesPage";
import PromotionPage from "./pages/institution/PromotionPage";
import FeesPage from "./pages/institution/fees/FeesPage";
import AITutorTeacher from "./pages/ai/AITutorTeacher";
import AITutorAdmin from "./pages/ai/AITutorAdmin";
import CurriculumDetailPage from "./pages/ai/CurriculumDetailPage";
import ParentPortal from "./pages/parent/ParentPortal";
import { plansConfig } from "./pages/platform/config";
import {
  usersConfig, subjectsConfig, noticesConfig,
  academicYearsConfig, academicUnitsConfig,
} from "./pages/institution/config";

const Loader = () => (
  <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-[#0B0F17]">
    <div className="h-8 w-8 rounded-lg bg-indigo-600 animate-pulse" />
  </div>
);

const Protected = ({ roles, children }) => {
  const { user } = useAuth();
  const location = useLocation();
  if (user === null) return <Loader />;
  if (user === false) return <Navigate to="/login" replace />;
  if (user.must_change_password && location.pathname !== "/change-password") return <Navigate to="/change-password" replace />;
  if (roles && !roles.includes(user.role)) return <Navigate to="/access-denied" replace />;
  return children;
};

const RootRedirect = () => {
  const { user } = useAuth();
  if (user === null) return <Loader />;
  if (user === false) return <Navigate to="/login" replace />;
  return <Navigate to={roleHome(user.role)} replace />;
};

// /app/dashboard renders the admin dashboard for admins and the scoped overview for principals.
const DashboardRouter = () => {
  const { user } = useAuth();
  return user?.is_principal ? <PrincipalDashboard /> : <InstitutionDashboard />;
};

function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <ReportIssueProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<RootRedirect />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/lnmoplatformlogin" element={<LoginPage platform />} />
            <Route path="/login/:slug" element={<LoginPage />} />
            <Route path="/access-denied" element={<AccessDeniedPage />} />
            <Route path="/setup/parent" element={<ParentSetupPage />} />
            <Route path="/fees/invoice/:token" element={<FeeLinkPage />} />
            <Route path="/reset-password/:token" element={<ResetPasswordPage />} />
            <Route path="/setup/parent/:token" element={<ParentSetupPage />} />
            <Route path="/change-password" element={<Protected><ChangePasswordPage /></Protected>} />
            <Route
              path="/portal/*"
              element={<Protected roles={["student", "staff"]}><StudentPortal /></Protected>}
            />
            <Route path="/portal-coming-soon" element={<Navigate to="/portal" replace />} />
            <Route path="/parents/*" element={<Protected roles={["parent"]}><ParentPortal /></Protected>} />

            <Route
              path="/platform"
              element={<Protected roles={["platform_admin"]}><AppShell nav={platformNav} consoleLabel="Platform Console" /></Protected>}
            >
              <Route index element={<Navigate to="/platform/dashboard" replace />} />
              <Route path="dashboard" element={<PlatformDashboard />} />
              <Route path="institutions" element={<PlatformInstitutionsPage />} />
              <Route path="institutions/:id" element={<InstitutionDetail />} />
              <Route path="plans" element={<ResourcePage {...plansConfig} />} />
              <Route path="communication" element={<PlatformCommunication />} />
              <Route path="library" element={<PlatformLibrary />} />
              <Route path="settings" element={<PlatformSettings />} />
              <Route path="issues" element={<PlatformIssues />} />
              <Route path="audit" element={<AuditPage />} />
            </Route>

            <Route
              path="/app/setup"
              element={<Protected roles={["institution_admin"]}><SetupWizard /></Protected>}
            />

            <Route
              path="/app"
              element={<Protected roles={["institution_admin", "teacher"]}><InstitutionLayout /></Protected>}
            >
              <Route index element={<Navigate to="/app/dashboard" replace />} />
              <Route path="dashboard" element={<DashboardRouter />} />
              <Route path="class-hub" element={<ClassHub />} />
              <Route path="class-hub/:classId" element={<ClassDetailPage />} />
              <Route path="class-hub/:classId/section/:sectionId" element={<SectionDetailPage />} />
              <Route path="timetable" element={<TimetablePage />} />
              <Route path="substitutions" element={<SubstitutionsPage />} />
              <Route path="homework-monitor" element={<AdminOrPrincipal><HomeworkMonitor /></AdminOrPrincipal>} />
              <Route path="communication" element={<AdminOrPrincipal><CommunicationPage /></AdminOrPrincipal>} />
              <Route path="notifications" element={<NotificationsPage />} />
              <Route path="students" element={<StudentsPage />} />
              <Route path="students/:id" element={<AdminOrPrincipal><StudentProfileView /></AdminOrPrincipal>} />
              <Route path="teachers" element={<TeachersPage />} />
              <Route path="teachers/:id" element={<AdminOrPrincipal><TeacherProfileView /></AdminOrPrincipal>} />
              <Route path="principals" element={<AdminOnly><PrincipalsPage /></AdminOnly>} />
              <Route path="users" element={<AdminOnly><UsersPage /></AdminOnly>} />
              <Route path="classes" element={<Navigate to="/app/class-hub" replace />} />
              <Route path="sections" element={<Navigate to="/app/class-hub" replace />} />
              <Route path="subjects" element={<ResourcePage {...subjectsConfig} headerExtra={({ reload }) => <SubjectImportButton onDone={reload} />} />} />
              <Route path="academic-years" element={<AdminOnly><ResourcePage {...academicYearsConfig} /></AdminOnly>} />
              <Route path="academic-units" element={<AdminOnly><ResourcePage {...academicUnitsConfig} /></AdminOnly>} />
              <Route path="promotion" element={<AdminOrPrincipal><PromotionPage /></AdminOrPrincipal>} />
              <Route path="fees" element={<AdminOrPrincipal><FeesPage /></AdminOrPrincipal>} />
              <Route path="enrollments" element={<Navigate to="/app/class-hub" replace />} />
              <Route path="teacher-assignments" element={<Navigate to="/app/class-hub" replace />} />
              <Route path="attendance" element={<AttendancePage />} />
              <Route path="notices" element={<NoticesPage />} />
              <Route path="ai-tutor" element={<AITutorAdmin />} />
              <Route path="ai-tutor/curriculum/:cid" element={<CurriculumDetailPage />} />
              <Route path="assessments" element={<AssessmentsPage />} />
              <Route path="exams" element={<ExamsPage />} />
              <Route path="exams/:examId" element={<ExamDetailPage />} />
              <Route path="assessments/:id/marks" element={<MarksEntryPage />} />
              <Route path="audit" element={<AuditPage />} />
              <Route path="settings" element={<AdminOnly><InstitutionSettingsPage /></AdminOnly>} />
              <Route path="support" element={<AdminOrPrincipal><SupportPage /></AdminOrPrincipal>} />
              <Route path="_crash-test" element={<AdminOnly><CrashTest /></AdminOnly>} />
            </Route>

            <Route
              path="/teacher"
              element={<Protected roles={["teacher"]}><TeacherShell /></Protected>}
            >
              <Route index element={<Navigate to="/teacher/dashboard" replace />} />
              <Route path="dashboard" element={<TeacherDashboard />} />
              <Route path="students" element={<TeacherStudents />} />
              <Route path="timetable" element={<TeacherTimetable />} />
              <Route path="substitutions" element={<TeacherSubstitutions />} />
              <Route path="notifications" element={<NotificationsPage />} />
              <Route path="my-class" element={<TeacherMyClass />} />
              <Route path="marks" element={<TeacherMarksList />} />
              <Route path="marks/:id" element={<MarksEntryPage teacherMode />} />
              <Route path="homework" element={<TeacherHomework />} />
              <Route path="assignments" element={<TeacherAssignments />} />
              <Route path="notices" element={<NoticesPage />} />
              <Route path="ai-tutor" element={<AITutorTeacher />} />
              <Route path="ai-tutor/curriculum/:cid" element={<CurriculumDetailPage />} />
              <Route path="profile" element={<TeacherProfile />} />
              <Route path="attendance" element={<AttendancePage teacherMode />} />
              <Route path="fee-defaulters" element={<TeacherFeeDefaulters />} />
            </Route>

            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </BrowserRouter>
        </ReportIssueProvider>
        <Toaster richColors position="top-right" />
      </AuthProvider>
    </ThemeProvider>
  );
}

export default App;
