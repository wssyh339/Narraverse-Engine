import { useMutation } from "@tanstack/react-query";
import { Alert, App, Button, Card, Form, InputNumber, List, Progress, Space, Tag, Typography } from "antd";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { studioApi } from "../api/studio";
import type { GenerationJob } from "../types/api";

export function BatchPage() {
  const { projectId = "" } = useParams();
  const { message } = App.useApp();
  const [form] = Form.useForm<{ chapter_start: number; chapter_end: number }>();
  const [job, setJob] = useState<GenerationJob | null>(null);
  const mutation = useMutation({
    mutationFn: (values: { chapter_start: number; chapter_end: number }) => studioApi.batchGenerate(projectId, values.chapter_start, values.chapter_end),
    onSuccess: (result) => {
      setJob(result.job);
      message.success("批量生成完成");
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "批量生成失败"),
  });
  const controlMutation = useMutation({
    mutationFn: ({ action, jobId }: { action: "pause" | "resume" | "cancel"; jobId: string }) => {
      if (action === "pause") return studioApi.pauseJob(jobId, "从批量监控页暂停");
      if (action === "resume") return studioApi.resumeJob(jobId, "从批量监控页恢复");
      return studioApi.cancelJob(jobId, "从批量监控页取消");
    },
    onSuccess: ({ job: nextJob }, variables) => {
      setJob(nextJob);
      const labels = { pause: "任务已暂停", resume: "任务已恢复", cancel: "任务已取消" };
      message.success(labels[variables.action]);
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "任务状态更新失败"),
  });
  const totalSteps = Math.max(job?.progress.total_steps ?? 0, 1);
  const completedSteps = job?.progress.completed_steps ?? 0;
  const percent = job?.status === "succeeded" ? 100 : Math.round((completedSteps / totalSteps) * 100);
  const control = (action: "pause" | "resume" | "cancel") => {
    if (job) controlMutation.mutate({ action, jobId: job.id });
  };

  return (
    <Space direction="vertical" size={18} className="page-stack">
      <div className="page-heading">
        <div>
          <Typography.Title level={2}>批量生成与监控</Typography.Title>
          <Typography.Text type="secondary">选择章节范围，系统会逐章运行多 Agent 工作流并保存版本快照。</Typography.Text>
        </div>
      </div>
      <Card>
        <Form
          layout="inline"
          form={form}
          initialValues={{ chapter_start: 1, chapter_end: 3 }}
          onFinish={(values) => mutation.mutate(values)}
        >
          <Form.Item name="chapter_start" label="起始章节" rules={[{ required: true, message: "请输入起始章节" }]}>
            <InputNumber min={1} />
          </Form.Item>
          <Form.Item
            name="chapter_end"
            label="结束章节"
            dependencies={["chapter_start"]}
            rules={[
              { required: true, message: "请输入结束章节" },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  return !value || value >= getFieldValue("chapter_start")
                    ? Promise.resolve()
                    : Promise.reject(new Error("结束章节不能小于起始章节"));
                },
              }),
            ]}
          >
            <InputNumber min={1} />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={mutation.isPending} disabled={controlMutation.isPending}>
            开始批量生成
          </Button>
        </Form>
      </Card>
      {mutation.error ? <Alert type="error" message="批量生成失败" showIcon /> : null}
      <Card
        title="任务进度"
        extra={job ? <Tag color={job.status === "succeeded" ? "success" : job.status === "cancelled" ? "error" : "processing"}>{job.status}</Tag> : null}
      >
        <Progress
          percent={percent}
          status={mutation.error ? "exception" : mutation.isPending || job?.status === "running" ? "active" : undefined}
        />
        <Space wrap style={{ marginBottom: 12 }}>
          <Button disabled={!job || job.status === "paused" || job.status === "cancelled"} loading={controlMutation.isPending} onClick={() => control("pause")}>暂停</Button>
          <Button disabled={!job || job.status !== "paused"} loading={controlMutation.isPending} onClick={() => control("resume")}>恢复</Button>
          <Button danger disabled={!job || job.status === "cancelled"} loading={controlMutation.isPending} onClick={() => control("cancel")}>取消</Button>
        </Space>
        <List
          dataSource={mutation.data?.chapters ?? []}
          locale={{ emptyText: mutation.isPending ? "正在生成章节..." : "尚未创建批量任务" }}
          renderItem={(chapter) => <List.Item>{chapter.chapter_no}. {chapter.title} <Typography.Text type="secondary">{chapter.status}</Typography.Text></List.Item>}
        />
      </Card>
    </Space>
  );
}
