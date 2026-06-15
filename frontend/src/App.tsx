import { App as AntdApp, ConfigProvider, theme } from "antd";
import zhCN from "antd/locale/zh_CN";
import { lazy, Suspense, useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes, useParams } from "react-router-dom";
import { StudioLayout } from "./layouts/StudioLayout";
import { useStudioStore } from "./store/studioStore";

const DashboardPage = lazy(() => import("./pages/DashboardPage").then((module) => ({ default: module.DashboardPage })));
const ProjectCreateWizard = lazy(() => import("./pages/ProjectCreateWizard").then((module) => ({ default: module.ProjectCreateWizard })));
const WorkspacePage = lazy(() => import("./pages/WorkspacePage").then((module) => ({ default: module.WorkspacePage })));
const ProjectProfilePage = lazy(() => import("./pages/ProjectProfilePage").then((module) => ({ default: module.ProjectProfilePage })));
const OutlineStudioPage = lazy(() => import("./pages/OutlineStudioPage").then((module) => ({ default: module.OutlineStudioPage })));
const NotesStudioPage = lazy(() => import("./pages/NotesStudioPage").then((module) => ({ default: module.NotesStudioPage })));
const AgentsPage = lazy(() => import("./pages/AgentsPage").then((module) => ({ default: module.AgentsPage })));
const VersionsPage = lazy(() => import("./pages/VersionsPage").then((module) => ({ default: module.VersionsPage })));
const SettingsWorkbenchPage = lazy(() => import("./pages/SettingsWorkbenchPage").then((module) => ({ default: module.SettingsWorkbenchPage })));
const CharactersPage = lazy(() => import("./pages/CharactersPage").then((module) => ({ default: module.CharactersPage })));
const GraphPage = lazy(() => import("./pages/GraphPage").then((module) => ({ default: module.GraphPage })));
const WorldPage = lazy(() => import("./pages/WorldPage").then((module) => ({ default: module.WorldPage })));
const ForeshadowingPage = lazy(() => import("./pages/ForeshadowingPage").then((module) => ({ default: module.ForeshadowingPage })));
const BatchPage = lazy(() => import("./pages/BatchPage").then((module) => ({ default: module.BatchPage })));
const ExportPage = lazy(() => import("./pages/ExportPage").then((module) => ({ default: module.ExportPage })));
const JobPage = lazy(() => import("./pages/JobPage").then((module) => ({ default: module.JobPage })));

function ProjectSettingsRedirect() {
  const { projectId = "" } = useParams();
  return <Navigate to={`/projects/${projectId}/settings/tree`} replace />;
}

function ProjectSettingsSectionRedirect({ section }: { section: "profile" | "characters" | "world" | "graph" | "foreshadowing" }) {
  const { projectId = "" } = useParams();
  return <Navigate to={`/projects/${projectId}/settings/${section}`} replace />;
}

export function navigateTo(path: string): void {
  window.history.pushState({}, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export default function App() {
  const appearanceMode = useStudioStore((state) => state.appearanceMode);
  const darkMode = appearanceMode === "dark";
  const eyeCareMode = appearanceMode === "eye-care";

  useEffect(() => {
    document.documentElement.dataset.theme = darkMode ? "dark" : "light";
    document.documentElement.dataset.eyeCare = eyeCareMode ? "true" : "false";
  }, [appearanceMode, darkMode, eyeCareMode]);

  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: darkMode ? theme.darkAlgorithm : theme.defaultAlgorithm,
        token: {
          borderRadius: 10,
          colorBgBase: eyeCareMode ? (darkMode ? "#151d15" : "#f8fbef") : undefined,
          colorPrimary: eyeCareMode ? (darkMode ? "#9cc77b" : "#527a3f") : "#0f766e",
          colorInfo: eyeCareMode ? (darkMode ? "#9cc77b" : "#527a3f") : "#0f766e",
          colorSuccess: eyeCareMode ? (darkMode ? "#9cc77b" : "#527a3f") : "#0f766e",
          fontFamily: "ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif",
        },
      }}
    >
      <AntdApp>
        <Suspense fallback={<div className="route-loading">正在加载页面...</div>}>
          <BrowserRouter>
            <Routes>
              <Route element={<StudioLayout />}>
                <Route path="/" element={<DashboardPage />} />
                <Route path="/projects/new" element={<ProjectCreateWizard />} />
                <Route path="/projects/:projectId/workspace" element={<WorkspacePage />} />
                <Route path="/projects/:projectId/project" element={<ProjectSettingsSectionRedirect section="profile" />} />
                <Route path="/projects/:projectId/outline" element={<OutlineStudioPage />} />
                <Route path="/projects/:projectId/agents" element={<AgentsPage />} />
                <Route path="/projects/:projectId/versions" element={<VersionsPage />} />
                <Route path="/projects/:projectId/notes" element={<NotesStudioPage />} />
                <Route path="/projects/:projectId/batch" element={<BatchPage />} />
                <Route path="/projects/:projectId/export" element={<ExportPage />} />
                <Route path="/projects/:projectId/settings" element={<ProjectSettingsRedirect />} />
                <Route path="/projects/:projectId/settings/tree" element={<SettingsWorkbenchPage />} />
                <Route path="/projects/:projectId/settings/profile" element={<ProjectProfilePage />} />
                <Route path="/projects/:projectId/settings/characters" element={<CharactersPage />} />
                <Route path="/projects/:projectId/settings/world" element={<WorldPage />} />
                <Route path="/projects/:projectId/settings/graph" element={<GraphPage />} />
                <Route path="/projects/:projectId/settings/foreshadowing" element={<ForeshadowingPage />} />
                <Route path="/projects/:projectId/characters" element={<ProjectSettingsSectionRedirect section="characters" />} />
                <Route path="/projects/:projectId/graph" element={<ProjectSettingsSectionRedirect section="graph" />} />
                <Route path="/projects/:projectId/world" element={<ProjectSettingsSectionRedirect section="world" />} />
                <Route path="/projects/:projectId/foreshadowing" element={<ProjectSettingsSectionRedirect section="foreshadowing" />} />
                <Route path="/jobs/:jobId" element={<JobPage />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Route>
            </Routes>
          </BrowserRouter>
        </Suspense>
      </AntdApp>
    </ConfigProvider>
  );
}
