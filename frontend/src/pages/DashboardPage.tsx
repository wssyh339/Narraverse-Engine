import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { Button, Card, Col, Dropdown, Empty, Modal, Row, Skeleton, Space, Statistic, Tag, Typography, message } from "antd";
import { MoreHorizontal, Plus, Trash2 } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { studioApi, type CreateProjectPayload } from "../api/studio";
import { useStudioStore } from "../store/studioStore";

const creationStarDraftProject: CreateProjectPayload = {
  title: "未命名创作 Star 项目",
  genre: "待定",
  target_reader: "类型小说读者",
  premise: "通过创作 Star 抽卡确定作品方向。",
  style_guide: "清晰、有钩子。",
  language: "zh-CN",
  planned_chapter_count: 80,
  chapter_word_target: 2200,
  target_words: 176000,
  initial_idea: "",
};

export function DashboardPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
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

  return (
    <Space direction="vertical" size={18} className="page-stack">
      <div className="page-heading">
        <div>
          <Typography.Title level={2}>项目首页</Typography.Title>
          <Typography.Text type="secondary">管理本地小说项目、查看写作进度，并继续最近工作。</Typography.Text>
        </div>
        <Button type="primary" icon={<Plus size={16} />} loading={createStarProject.isPending} onClick={() => createStarProject.mutate()}>
          创建新项目
        </Button>
      </div>

      {query.isLoading ? <Skeleton active paragraph={{ rows: 6 }} /> : null}
      {query.error ? (
        <Card>
          <Empty description="无法连接后端服务，请确认后端已启动。" />
        </Card>
      ) : null}

      {query.data ? (
        <>
          <Row gutter={16}>
            <Col xs={24} md={8}>
              <Card><Statistic title="项目总数" value={query.data.stats.project_count ?? query.data.projects.length} /></Card>
            </Col>
            <Col xs={24} md={8}>
              <Card><Statistic title="活跃项目" value={query.data.stats.active_count ?? 0} /></Card>
            </Col>
            <Col xs={24} md={8}>
              <Card><Statistic title="计划总字数" value={query.data.stats.target_words ?? 0} /></Card>
            </Col>
          </Row>

          {query.data.projects.length === 0 ? (
            <Card>
              <Empty
                description="还没有项目，创建一个新项目开始。"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              >
                <Button type="primary" icon={<Plus size={16} />} loading={createStarProject.isPending} onClick={() => createStarProject.mutate()}>
                  创建新项目
                </Button>
              </Empty>
            </Card>
          ) : (
            <Row gutter={[16, 16]}>
              {query.data.projects.map((project) => (
                <Col key={project.id} xs={24} lg={8}>
                  <Card
                    className="project-card"
                    title={project.title}
                    extra={
                      <Space>
                        <Tag color={project.status === "archived" ? "default" : "green"}>{project.status}</Tag>
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
                      </Space>
                    }
                    actions={[
                      <Button
                        type="link"
                        key="open"
                        onClick={() => {
                          setCurrentProjectId(project.id);
                          message.success("已打开项目");
                          navigate(`/projects/${project.id}/workspace`);
                        }}
                      >
                        打开工作台
                      </Button>,
                    ]}
                  >
                    <Space direction="vertical">
                      <Typography.Text>{project.premise}</Typography.Text>
                      <Typography.Text type="secondary">{project.genre} · {project.planned_chapter_count} 章 · 单章 {project.chapter_word_target} 字</Typography.Text>
                      <Typography.Text type="secondary">更新：{project.updated_at}</Typography.Text>
                    </Space>
                  </Card>
                </Col>
              ))}
            </Row>
          )}
        </>
      ) : null}
    </Space>
  );
}
