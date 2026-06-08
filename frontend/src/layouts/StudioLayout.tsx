import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Bot,
  Boxes,
  FileText,
  Focus,
  GitBranch,
  Home,
  ListTree,
  Moon,
  Network,
  NotebookPen,
  Settings,
  Star,
  Sun,
  Upload,
  Users,
} from "lucide-react";
import { Button, Layout, Menu, Space, Tag, Typography, theme } from "antd";
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
  const darkMode = useStudioStore((state) => state.darkMode);
  const focusMode = useStudioStore((state) => state.focusMode);
  const toggleDarkMode = useStudioStore((state) => state.toggleDarkMode);
  const toggleFocusMode = useStudioStore((state) => state.toggleFocusMode);
  const [creationStarOpen, setCreationStarOpen] = useState(false);
  const { token } = theme.useToken();
  const projectQuery = useQuery({
    queryKey: ["project-shell", projectId],
    queryFn: () => studioApi.getProject(projectId!),
    enabled: Boolean(projectId && isProjectStudio),
  });

  const projectPath = (suffix: string) => (projectId ? `/projects/${projectId}${suffix}` : "/");
  const primaryItems: MenuProps["items"] = [
    { key: "creation-star", icon: <Star size={16} />, label: "创作 Star" },
    { key: projectPath("/project"), icon: <FileText size={16} />, label: "作品" },
    { key: projectPath("/workspace"), icon: <NotebookPen size={16} />, label: "正文" },
    { key: projectPath("/characters"), icon: <Boxes size={16} />, label: "设定" },
    { key: projectPath("/outline"), icon: <ListTree size={16} />, label: "大纲" },
    { key: projectPath("/notes"), icon: <NotebookPen size={16} />, label: "笔记" },
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
    navigate(key);
  };

  const invalidateProjectStudio = () => {
    if (!projectId) return;
    queryClient.invalidateQueries({ queryKey: ["project-shell", projectId] });
    queryClient.invalidateQueries({ queryKey: ["state", projectId] });
    queryClient.invalidateQueries({ queryKey: ["projects"] });
  };
  const toolItems: MenuProps["items"] = [
    { key: projectPath("/agents"), icon: <Bot size={16} />, label: "Agent" },
    { key: projectPath("/versions"), icon: <GitBranch size={16} />, label: "版本" },
    { key: projectPath("/graph"), icon: <Network size={16} />, label: "图谱" },
    { key: projectPath("/world"), icon: <Boxes size={16} />, label: "世界" },
    { key: projectPath("/foreshadowing"), icon: <Settings size={16} />, label: "伏笔" },
    { key: projectPath("/batch"), icon: <Bot size={16} />, label: "批量" },
    { key: projectPath("/export"), icon: <Upload size={16} />, label: "导出" },
  ];

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
            selectedKeys={[location.pathname]}
            items={primaryItems}
            onClick={handleProjectMenuClick}
            className="project-studio-tabs"
          />
          <Space>
            <Tag color="green">自动保存</Tag>
            <Button icon={<Focus size={16} />} type={focusMode ? "primary" : "default"} onClick={toggleFocusMode}>
              {focusMode ? "退出专注" : "专注写作"}
            </Button>
            <Button icon={darkMode ? <Sun size={16} /> : <Moon size={16} />} onClick={toggleDarkMode} title="切换主题" />
          </Space>
        </Header>
        {!focusMode ? (
          <div className="project-tool-strip">
            <Menu mode="horizontal" selectedKeys={[location.pathname]} items={toolItems} onClick={({ key }) => navigate(key)} />
            <Typography.Text type="secondary">本地优先 · 所有 AI 写入先预览再应用</Typography.Text>
          </div>
        ) : null}
        <Content className="project-studio-content">
          <Outlet />
        </Content>
        {projectId ? (
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
    { key: projectId ? projectPath("/characters") : "recent-settings", icon: <Users size={17} />, label: "最近项目设定", disabled: !projectId },
  ];

  return (
    <Layout className="studio-shell">
      <Sider width={236} className="studio-sider">
        <div className="brand">
          <div className="brand-icon">NS</div>
          <div>
            <Typography.Text strong>Novel Studio</Typography.Text>
            <Typography.Text type="secondary">专业长篇创作工作室</Typography.Text>
          </div>
        </div>
        <Menu mode="inline" selectedKeys={[location.pathname]} items={dashboardItems} onClick={({ key }) => navigate(key)} className="studio-menu" />
      </Sider>
      <Layout>
        <Header className="studio-header" style={{ background: token.colorBgContainer }}>
          <Typography.Text type="secondary">本地优先 · LangGraph 多 Agent · 动态设定集</Typography.Text>
          <Button icon={darkMode ? <Sun size={16} /> : <Moon size={16} />} onClick={toggleDarkMode}>{darkMode ? "亮色" : "暗色"}</Button>
        </Header>
        <Content className="studio-content"><Outlet /></Content>
      </Layout>
    </Layout>
  );
}
