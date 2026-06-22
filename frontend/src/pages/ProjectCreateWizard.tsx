import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Result, Space, Typography, message } from "antd";
import { Sparkles } from "lucide-react";
import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { studioApi, type CreateProjectPayload } from "../api/studio";
import { CreationStarWizard } from "../components/CreationStarWizard";
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

export function ProjectCreateWizard() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const setCurrentProjectId = useStudioStore((state) => state.setCurrentProjectId);
  const nextInFlightRef = useRef(false);
  const [projectId, setProjectId] = useState("");
  const [openStar, setOpenStar] = useState(false);
  const [createError, setCreateError] = useState("");
  const mutation = useMutation({ mutationFn: studioApi.createProject });

  async function startCreationStar() {
    if (nextInFlightRef.current || mutation.isPending) return;
    try {
      nextInFlightRef.current = true;
      setCreateError("");
      const { project } = await mutation.mutateAsync(creationStarDraftProject);
      setProjectId(project.id);
      setCurrentProjectId(project.id);
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      setOpenStar(true);
      message.success("草稿项目已创建，请继续完成创作 Star 抽卡");
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "创建项目失败，请确认后端服务已启动。";
      setCreateError(errorMessage);
      message.error(errorMessage);
    } finally {
      nextInFlightRef.current = false;
    }
  }

  return (
    <Space direction="vertical" size={18} className="page-stack">
      <div className="page-heading">
        <div>
          <Typography.Title level={2}>创建小说项目</Typography.Title>
          <Typography.Text type="secondary">新项目将通过创作 Star 完成频道、类型、世界观、人设、书名和总设定抽卡。</Typography.Text>
        </div>
      </div>
      <Card>
        {createError ? <Alert type="error" showIcon message="创建项目失败" description={createError} style={{ marginBottom: 16 }} /> : null}
        <Result
          icon={<Sparkles size={52} />}
          title="使用创作 Star 创建新项目"
          subTitle="先创建本地草稿项目，再进入抽卡式立项流程。最终确认后会写入作品信息和设定集。"
          extra={[
            <Button key="start" type="primary" size="large" loading={mutation.isPending} onClick={startCreationStar}>
              开始创作 Star
            </Button>,
            <Button key="back" onClick={() => navigate("/")}>返回项目首页</Button>,
          ]}
        />
      </Card>
      {projectId ? (
        <CreationStarWizard
          projectId={projectId}
          open={openStar}
          onClose={() => setOpenStar(false)}
          onCommitted={() => {
            queryClient.invalidateQueries({ queryKey: ["projects"] });
            navigate(`/projects/${projectId}/workspace`);
          }}
        />
      ) : null}
    </Space>
  );
}
