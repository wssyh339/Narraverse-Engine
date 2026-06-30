import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { App, Button, Dropdown, Empty, Modal, Skeleton, Space, Tag, Typography } from "antd";
import { BookOpen, Clock3, Feather, LibraryBig, MoreHorizontal, Play, Plus, Trash2 } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { studioApi, type CreateProjectPayload } from "../api/studio";
import { useStudioStore } from "../store/studioStore";

const DEFAULT_CHAPTER_WORD_TARGET = 8000;
const creationStarDraftProject: CreateProjectPayload = {
  title: "未命名创作 Star 项目",
  genre: "待定",
  target_reader: "类型小说读者",
  premise: "通过创作 Star 抽卡确定作品方向。",
  style_guide: "清晰、有钩子。",
  language: "zh-CN",
  planned_chapter_count: 80,
  chapter_word_target: DEFAULT_CHAPTER_WORD_TARGET,
  target_words: 80 * DEFAULT_CHAPTER_WORD_TARGET,
  initial_idea: "",
};

const formatNumber = (value: number) => new Intl.NumberFormat("zh-CN").format(value);

export function DashboardPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { message } = App.useApp();
  const currentProjectId = useStudioStore((state) => state.currentProjectId);
  const setCurrentProjectId = useStudioStore((state) => state.setCurrentProjectId);
  const setRecentProjects = useStudioStore((state) => state.setRecentProjects);
  const query = useQuery({
    queryKey: ["projects"],
    queryFn: studioApi.listProjects,
  });
  const deleteMutation = useMutation({
    mutationFn: (projectId: string) => studioApi.deleteProject(projectId),
    onSuccess: ({ project_id }) => {
      if (currentProjectId === project_id) {
        setCurrentProjectId(null);
      }
      message.success("项目已删除");
      queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "项目删除失败"),
  });
  const createStarProject = useMutation({
    mutationFn: () => studioApi.createProject(creationStarDraftProject),
    onSuccess: ({ project }) => {
      setCurrentProjectId(project.id);
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      message.success("已创建草稿项目，请用创作 Star 完成设定");
      navigate(`/projects/${project.id}/workspace?creationStar=1`);
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "创建项目失败，请确认后端服务已启动。"),
  });

  useEffect(() => {
    if (query.data) {
      setRecentProjects(query.data.projects);
    }
  }, [query.data, setRecentProjects]);

  const projects = query.data?.projects ?? [];
  const stats = query.data?.stats;
  const latestProject = projects.find((project) => project.id === currentProjectId) ?? projects[0];
  const projectCount = stats?.project_count ?? projects.length;
  const activeCount = stats?.active_count ?? projects.filter((project) => project.status === "active").length;
  const targetWords = stats?.target_words ?? projects.reduce((sum, project) => sum + (project.target_words ?? 0), 0);

  return (
    <div className="dashboard-page">
      <section className="dashboard-hero">
        <div className="dashboard-hero-copy">
          <Typography.Title level={1}>作品中枢</Typography.Title>
          <Typography.Paragraph>
            从创作 Star 立项、Agent 议事到章节闭环，把世界观、人物和版本证据收进同一套本地正典。
          </Typography.Paragraph>
          <Space wrap size={10} className="dashboard-hero-actions">
            <Button type="primary" size="large" icon={<Plus size={17} />} loading={createStarProject.isPending} onClick={() => createStarProject.mutate()}>
              创建新项目
            </Button>
            {latestProject ? (
              <Button
                size="large"
                icon={<Play size={16} />}
                onClick={() => {
                  setCurrentProjectId(latestProject.id);
                  navigate(`/projects/${latestProject.id}/workspace`);
                }}
              >
                继续最近创作
              </Button>
            ) : null}
          </Space>
        </div>
        <div className="dashboard-hero-panel" aria-label="创作工作室概览">
          <div className="hero-panel-topline">
            <span>叙界推演引擎</span>
            <Tag color="green">正典闭环</Tag>
          </div>
          <div className="hero-panel-focus">
            <Feather size={24} />
            <div>
              <Typography.Text strong>一部小说，一条可追溯生产线</Typography.Text>
              <Typography.Text type="secondary">抽卡、议事、正文、设定更新和回滚都绑定项目上下文。</Typography.Text>
            </div>
          </div>
          <div className="dashboard-stat-rail">
            <div>
              <span>{formatNumber(projectCount)}</span>
              <small>作品档案</small>
            </div>
            <div>
              <span>{formatNumber(activeCount)}</span>
              <small>创作中</small>
            </div>
            <div>
              <span>{formatNumber(targetWords)}</span>
              <small>目标字数</small>
            </div>
          </div>
        </div>
      </section>

      {query.isLoading ? (
        <div className="dashboard-loading">
          <Skeleton active paragraph={{ rows: 6 }} />
        </div>
      ) : null}
      {query.error ? (
        <div className="dashboard-state-panel">
          <Empty description="无法连接后端服务，请确认后端已启动。" />
        </div>
      ) : null}

      {query.data ? (
        <>
          {projects.length === 0 ? (
            <div className="dashboard-empty">
              <div className="dashboard-empty-mark">
                <BookOpen size={30} />
              </div>
              <Empty
                description="还没有项目，创建一个新项目开始。"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              >
                <Button type="primary" size="large" icon={<Plus size={16} />} loading={createStarProject.isPending} onClick={() => createStarProject.mutate()}>
                  创建新项目
                </Button>
              </Empty>
            </div>
          ) : (
            <section className="project-section">
              <div className="project-section-heading">
                <div>
                  <Typography.Title level={3}>作品库</Typography.Title>
                  <Typography.Text type="secondary">选择一个项目进入正文、设定和大纲工作流。</Typography.Text>
                </div>
                <Button icon={<LibraryBig size={16} />} onClick={() => queryClient.invalidateQueries({ queryKey: ["projects"] })}>
                  刷新列表
                </Button>
              </div>
              <div className="project-list-grid">
                {projects.map((project) => (
                  <article key={project.id} className="project-card">
                    <header className="project-card-header">
                      <div>
                        <Typography.Title level={4}>{project.title}</Typography.Title>
                        <Tag color={project.status === "archived" ? "default" : "green"}>{project.status}</Tag>
                      </div>
                      <Dropdown
                        trigger={["click"]}
                        menu={{
                          items: [
                            {
                              key: "delete",
                              danger: true,
                              icon: <Trash2 size={14} />,
                              label: "删除项目",
                              onClick: () => {
                                Modal.confirm({
                                  title: "删除项目？",
                                  content: `确认删除「${project.title}」吗？项目下的章节、角色、伏笔和版本快照都会移除。`,
                                  okText: "删除",
                                  okButtonProps: { danger: true, loading: deleteMutation.isPending },
                                  cancelText: "取消",
                                  onOk: () => deleteMutation.mutateAsync(project.id),
                                });
                              },
                            },
                          ],
                        }}
                      >
                        <Button type="text" icon={<MoreHorizontal size={16} />} />
                      </Dropdown>
                    </header>
                    <Typography.Paragraph className="project-card-premise" ellipsis={{ rows: 3 }}>
                      {project.premise}
                    </Typography.Paragraph>
                    <div className="project-card-meta">
                      <span><BookOpen size={14} />{project.genre}</span>
                      <span><LibraryBig size={14} />{project.planned_chapter_count} 章</span>
                      <span><Feather size={14} />单章 {project.chapter_word_target} 字</span>
                      <span><Clock3 size={14} />更新：{project.updated_at}</span>
                    </div>
                    <Button
                      type="primary"
                      block
                      onClick={() => {
                        setCurrentProjectId(project.id);
                        message.success("已打开项目");
                        navigate(`/projects/${project.id}/workspace`);
                      }}
                    >
                      打开工作台
                    </Button>
                  </article>
                ))}
              </div>
            </section>
          )}
        </>
      ) : null}
    </div>
  );
}
