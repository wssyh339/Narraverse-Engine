import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Bot,
  Boxes,
  Eye,
  Focus,
  GitBranch,
  Home,
  ListTree,
  Moon,
  NotebookPen,
  Star,
  Sun,
  Upload,
  Users,
} from "lucide-react";
import { Alert, Button, Layout, Menu, Space, Tag, Typography, theme } from "antd";
import type { MenuProps } from "antd";
import { lazy, Suspense, useEffect, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { studioApi } from "../api/studio";
import { useStudioStore } from "../store/studioStore";

const { Header, Sider, Content } = Layout;
const CreationStarWizard = lazy(() => import("../components/CreationStarWizard").then((module) => ({ default: module.CreationStarWizard })));

function projectIdFromPath(pathname: string) {
  return pathname.match(/^\/projects\/([^/]+)/)?.[1] ?? null;
}

export function StudioLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const pathProjectId = projectIdFromPath(location.pathname);
  const storedProjectId = useStudioStore((state) => state.currentProjectId);
  const projectId = pathProjectId && pathProjectId !== "new" ? pathProjectId : storedProjectId;
  const isProjectStudio = Boolean(pathProjectId && pathProjectId !== "new");
  const appearanceMode = useStudioStore((state) => state.appearanceMode);
  const focusMode = useStudioStore((state) => state.focusMode);
  const cycleAppearanceMode = useStudioStore((state) => state.cycleAppearanceMode);
  const toggleFocusMode = useStudioStore((state) => state.toggleFocusMode);
  const [creationStarOpen, setCreationStarOpen] = useState(false);
  const { token } = theme.useToken();
  const projectPath = (suffix: string) => (projectId ? `/projects/${projectId}${suffix}` : "/");
  const isSettingsPath = /\/projects\/[^/]+\/(settings|project|characters|graph|world|foreshadowing)(\/|$)/.test(location.pathname);
  const isWorkspacePath = projectId ? location.pathname === projectPath("/workspace") : false;
  const primarySelectedKey = isSettingsPath ? "settings" : location.pathname;
  const projectQuery = useQuery({
    queryKey: ["project-shell", projectId],
    queryFn: () => studioApi.getProject(projectId!),
    enabled: Boolean(projectId && isProjectStudio),
  });
  const llmModelsQuery = useQuery({
    queryKey: ["llm-models"],
    queryFn: studioApi.listLlmModels,
    enabled: isProjectStudio,
    staleTime: 60_000,
  });
  const llmConfigurationWarning = llmModelsQuery.data?.configuration_warning ?? "";

  const primaryItems: MenuProps["items"] = [
    { key: "creation-star", icon: <Star size={16} />, label: "创作 Star" },
    { key: projectPath("/outline"), icon: <ListTree size={16} />, label: "大纲" },
    { key: "settings", icon: <Boxes size={16} />, label: "设定" },
    { key: projectPath("/workspace"), icon: <NotebookPen size={16} />, label: "正文" },
    { key: projectPath("/agents"), icon: <Bot size={16} />, label: "Agent" },
  ];

  useEffect(() => {
    if (!isProjectStudio) return;
    const params = new URLSearchParams(location.search);
    if (params.get("creationStar") === "1") {
      setCreationStarOpen(true);
      navigate(location.pathname, { replace: true });
    }
  }, [isProjectStudio, location.pathname, location.search, navigate]);

  const handleProjectMenuClick: MenuProps["onClick"] = ({ key }) => {
    if (key === "creation-star") {
      setCreationStarOpen(true);
      return;
    }
    if (key === "settings") {
      navigate(projectPath("/settings/tree"));
      return;
    }
    navigate(key);
  };

  const invalidateProjectStudio = () => {
    if (!projectId) return;
    queryClient.invalidateQueries({ queryKey: ["project-shell", projectId] });
    queryClient.invalidateQueries({ queryKey: ["state", projectId] });
    queryClient.invalidateQueries({ queryKey: ["projects"] });
  };
  const toolItems: MenuProps["items"] = [
    { key: projectPath("/batch"), icon: <Bot size={16} />, label: "批量" },
    { key: projectPath("/notes"), icon: <NotebookPen size={16} />, label: "笔记" },
    { key: projectPath("/export"), icon: <Upload size={16} />, label: "导出" },
    { key: projectPath("/versions"), icon: <GitBranch size={16} />, label: "版本" },
  ];
  const appearanceControl = {
    light: {
      icon: <Sun size={16} />,
      label: "亮色",
      title: "当前亮色，点击切换到暗色",
    },
    dark: {
      icon: <Moon size={16} />,
      label: "暗色",
      title: "当前暗色，点击切换到护眼",
    },
    "eye-care": {
      icon: <Eye size={16} />,
      label: "护眼",
      title: "当前护眼，点击切换到亮色",
    },
  }[appearanceMode];

  if (isProjectStudio) {
    return (
      <Layout className={`studio-shell project-studio-shell ${focusMode ? "is-focus-mode" : ""}`}>
        <Header className="project-studio-header" style={{ background: token.colorBgContainer }}>
          <Space className="project-studio-brand">
            <Button type="text" icon={<ArrowLeft size={17} />} onClick={() => navigate("/")} title="返回项目首页" />
            <div>
              <Typography.Text strong>{projectQuery.data?.project.title ?? "创作工作室"}</Typography.Text>
              <Typography.Text type="secondary" className="project-studio-meta">
                {projectQuery.data?.project.genre ?? "本地项目"}
              </Typography.Text>
            </div>
          </Space>
          <Menu
            mode="horizontal"
            selectedKeys={[primarySelectedKey]}
            items={primaryItems}
            onClick={handleProjectMenuClick}
            className="project-studio-tabs"
          />
          <Space className="project-studio-actions">
            <Tag color="green" className="autosave-tag">自动保存</Tag>
            <Button icon={<Focus size={16} />} type={focusMode ? "primary" : "default"} onClick={toggleFocusMode}>
              {focusMode ? "退出专注" : "专注写作"}
            </Button>
            <Button
              icon={appearanceControl.icon}
              type={appearanceMode === "eye-care" ? "primary" : "default"}
              onClick={cycleAppearanceMode}
              title={appearanceControl.title}
            >
              {appearanceControl.label}
            </Button>
          </Space>
        </Header>
        {!focusMode && llmConfigurationWarning ? (
          <Alert
            className="llm-config-warning"
            type="warning"
            showIcon
            message="LLM 未配置"
            description={
              <Space wrap>
                <Typography.Text>{llmConfigurationWarning}</Typography.Text>
                <Tag>Provider: {llmModelsQuery.data?.default_provider ?? "未配置"}</Tag>
                <Tag>Model: {llmModelsQuery.data?.default_model ?? "未配置"}</Tag>
              </Space>
            }
          />
        ) : null}
        {!focusMode && isWorkspacePath ? (
          <div className="project-tool-strip">
            <Menu mode="horizontal" selectedKeys={[location.pathname]} items={toolItems} onClick={({ key }) => navigate(key)} />
            <Typography.Text type="secondary">本地优先 · 所有 AI 写入先预览再应用</Typography.Text>
          </div>
        ) : null}
        <Content className="project-studio-content">
          <Outlet />
        </Content>
        {projectId && creationStarOpen ? (
          <Suspense fallback={null}>
            <CreationStarWizard
              projectId={projectId}
              open={creationStarOpen}
              onClose={() => setCreationStarOpen(false)}
              onCommitted={invalidateProjectStudio}
            />
          </Suspense>
        ) : null}
      </Layout>
    );
  }

  const dashboardItems: MenuProps["items"] = [
    { key: "/", icon: <Home size={17} />, label: "项目首页" },
    { key: projectId ? projectPath("/workspace") : "recent-workspace", icon: <NotebookPen size={17} />, label: "继续最近创作", disabled: !projectId },
    { key: projectId ? projectPath("/settings/characters") : "recent-settings", icon: <Users size={17} />, label: "最近项目设定", disabled: !projectId },
  ];

  return (
    <Layout className="studio-shell">
      <Sider width={236} className="studio-sider">
        <div className="brand">
          <div className="brand-icon">NS</div>
          <div className="brand-copy">
            <Typography.Text strong>Novel Studio</Typography.Text>
            <Typography.Text type="secondary">专业长篇创作工作室</Typography.Text>
          </div>
        </div>
        <Menu mode="inline" selectedKeys={[location.pathname]} items={dashboardItems} onClick={({ key }) => navigate(key)} className="studio-menu" />
      </Sider>
      <Layout>
        <Header className="studio-header" style={{ background: token.colorBgContainer }}>
          <Typography.Text type="secondary" className="studio-header-signal">
            <span>本地优先</span>
            <span>LangGraph 多 Agent</span>
            <span>动态设定集</span>
          </Typography.Text>
          <Button
            className="studio-header-action"
            icon={appearanceControl.icon}
            type={appearanceMode === "eye-care" ? "primary" : "default"}
            onClick={cycleAppearanceMode}
            title={appearanceControl.title}
          >
            {appearanceControl.label}
          </Button>
        </Header>
        <Content className="studio-content"><Outlet /></Content>
      </Layout>
    </Layout>
  );
}
