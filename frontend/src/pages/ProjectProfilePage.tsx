import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Form, Input, InputNumber, Select, Space, Tabs, Typography, message } from "antd";
import { Save, Sparkles } from "lucide-react";
import { useEffect } from "react";
import { useParams } from "react-router-dom";
import { studioApi } from "../api/studio";
import type { Project, StoryBible } from "../types/api";

export function ProjectProfilePage() {
  const { projectId = "" } = useParams();
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["project-profile", projectId], queryFn: () => studioApi.getProject(projectId), enabled: !!projectId });
  const [projectForm] = Form.useForm<Partial<Project>>();
  const [bibleForm] = Form.useForm<Partial<StoryBible>>();

  useEffect(() => {
    if (query.data) {
      projectForm.setFieldsValue(query.data.project);
      bibleForm.setFieldsValue(query.data.story_bible);
    }
  }, [query.data, projectForm, bibleForm]);

  const saveProject = useMutation({
    mutationFn: (values: Partial<Project>) => studioApi.updateProject(projectId, values),
    onSuccess: () => {
      message.success("作品信息已保存");
      queryClient.invalidateQueries({ queryKey: ["project-profile", projectId] });
      queryClient.invalidateQueries({ queryKey: ["project-shell", projectId] });
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "保存失败"),
  });
  const saveBible = useMutation({
    mutationFn: (values: Partial<StoryBible>) => studioApi.updateStoryBible(projectId, values),
    onSuccess: () => {
      message.success("核心构架已保存");
      queryClient.invalidateQueries({ queryKey: ["project-profile", projectId] });
      queryClient.invalidateQueries({ queryKey: ["state", projectId] });
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "保存失败"),
  });
  const generate = useMutation({
    mutationFn: () => studioApi.generateStoryBible(projectId, query.data?.project.initial_idea ?? ""),
    onSuccess: () => {
      message.success("总策划 Agent 已生成核心构架");
      queryClient.invalidateQueries({ queryKey: ["project-profile", projectId] });
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "生成失败"),
  });

  if (query.isLoading) return <Card loading />;
  if (query.error || !query.data) return <Alert type="error" showIcon message="无法读取作品资料" />;

  return (
    <div className="studio-document-page">
      <div className="studio-page-heading">
        <div>
          <Typography.Title level={3}>作品资料</Typography.Title>
          <Typography.Text type="secondary">这里维护全书创作方向，所有 Agent 在生成前都会读取这些信息。</Typography.Text>
        </div>
        <Button icon={<Sparkles size={15} />} loading={generate.isPending} onClick={() => generate.mutate()}>总策划 Agent 辅助生成</Button>
      </div>
      <Tabs
        items={[
          {
            key: "basic",
            label: "基础信息",
            children: (
              <Card>
                <Form form={projectForm} layout="vertical" onFinish={(values) => saveProject.mutate(values)}>
                  <div className="form-grid-2">
                    <Form.Item name="title" label="书名" rules={[{ required: true }]}><Input /></Form.Item>
                    <Form.Item name="genre" label="题材赛道" rules={[{ required: true }]}><Input /></Form.Item>
                    <Form.Item name="planned_chapter_count" label="目标章节数"><InputNumber min={1} max={1000} className="full-width" /></Form.Item>
                    <Form.Item name="chapter_word_target" label="单章目标字数"><InputNumber min={500} max={20000} className="full-width" /></Form.Item>
                  </div>
                  <Form.Item name="target_reader" label="目标读者"><Input.TextArea rows={3} /></Form.Item>
                  <Form.Item name="premise" label="作品简介 / 核心卖点"><Input.TextArea rows={5} /></Form.Item>
                  <Form.Item name="initial_idea" label="初始创意"><Input.TextArea rows={5} /></Form.Item>
                  <Form.Item name="style_guide" label="文风说明"><Input.TextArea rows={4} /></Form.Item>
                  <Button type="primary" htmlType="submit" icon={<Save size={15} />} loading={saveProject.isPending}>保存作品信息</Button>
                </Form>
              </Card>
            ),
          },
          {
            key: "bible",
            label: "核心构架",
            children: (
              <Card>
                <Form form={bibleForm} layout="vertical" onFinish={(values) => saveBible.mutate(values)}>
                  <Form.Item name="world_setting" label="世界观设定"><Input.TextArea rows={7} /></Form.Item>
                  <Form.Item name="main_conflict" label="主线冲突"><Input.TextArea rows={5} /></Form.Item>
                  <Form.Item name="themes" label="主题"><Select mode="tags" /></Form.Item>
                  <Form.Item name="narrative_pov" label="叙事视角">
                    <Select options={[
                      { value: "first_person", label: "第一人称" },
                      { value: "third_person_limited", label: "第三人称有限" },
                      { value: "third_person_omniscient", label: "第三人称全知" },
                    ]} />
                  </Form.Item>
                  <Form.Item name="continuity_rules" label="连续性规则"><Select mode="tags" /></Form.Item>
                  <Form.Item name="forbidden_elements" label="禁止元素"><Select mode="tags" /></Form.Item>
                  <Button type="primary" htmlType="submit" icon={<Save size={15} />} loading={saveBible.isPending}>保存核心构架</Button>
                </Form>
              </Card>
            ),
          },
        ]}
      />
    </div>
  );
}
