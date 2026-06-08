import { App as AntdApp, ConfigProvider, theme } from "antd";
import zhCN from "antd/locale/zh_CN";
import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
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
const CharactersPage = lazy(() => import("./pages/CharactersPage").then((module) => ({ default: module.CharactersPage })));
const GraphPage = lazy(() => import("./pages/GraphPage").then((module) => ({ default: module.GraphPage })));
const WorldPage = lazy(() => import("./pages/WorldPage").then((module) => ({ default: module.WorldPage })));
const ForeshadowingPage = lazy(() => import("./pages/ForeshadowingPage").then((module) => ({ default: module.ForeshadowingPage })));
const BatchPage = lazy(() => import("./pages/BatchPage").then((module) => ({ default: module.BatchPage })));
const ExportPage = lazy(() => import("./pages/ExportPage").then((module) => ({ default: module.ExportPage })));
const JobPage = lazy(() => import("./pages/JobPage").then((module) => ({ default: module.JobPage })));

export function navigateTo(path: string): void {
  window.history.pushState({}, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export default function App() {
  const darkMode = useStudioStore((state) => state.darkMode);

  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: darkMode ? theme.darkAlgorithm : theme.defaultAlgorithm,
        token: {
          borderRadius: 8,
          colorPrimary: "#0f766e",
          fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', sans-serif",
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
                <Route path="/projects/:projectId/project" element={<ProjectProfilePage />} />
                <Route path="/projects/:projectId/outline" element={<OutlineStudioPage />} />
                <Route path="/projects/:projectId/notes" element={<NotesStudioPage />} />
                <Route path="/projects/:projectId/agents" element={<AgentsPage />} />
                <Route path="/projects/:projectId/versions" element={<VersionsPage />} />
                <Route path="/projects/:projectId/characters" element={<CharactersPage />} />
                <Route path="/projects/:projectId/graph" element={<GraphPage />} />
                <Route path="/projects/:projectId/world" element={<WorldPage />} />
                <Route path="/projects/:projectId/foreshadowing" element={<ForeshadowingPage />} />
                <Route path="/projects/:projectId/batch" element={<BatchPage />} />
                <Route path="/projects/:projectId/export" element={<ExportPage />} />
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
