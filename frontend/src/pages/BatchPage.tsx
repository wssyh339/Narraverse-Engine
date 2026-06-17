import { useMutation, useQuery } from "@tanstack/react-query";
import { Alert, App, Button, Card, Form, Input, InputNumber, List, Progress, Space, Tag, Typography } from "antd";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { studioApi } from "../api/studio";
import type { Chapter, GenerationJob } from "../types/api";

interface BatchChapterResult {
  chapter_no: number;
  chapter_id?: string;
  title?: string;
  status?: string;
  word_count?: number;
  job_id?: string | null;
  chapter?: Chapter;
}

interface BatchChapterFailure {
  chapter_no: number;
  message: string;
  failed_at?: string | null;
}

interface BatchJobResult {
  chapter_results?: BatchChapterResult[];
  failed_chapters?: BatchChapterFailure[];
  requested_range?: { chapter_start?: number; chapter_end?: number };
}

const activeStatuses = new Set(["queued", "running"]);
const terminalStatuses = new Set(["succeeded", "failed", "cancelled"]);

function asBatchResult(value: unknown): BatchJobResult {
  if (!value || typeof value !== "object") return {};
  const result = value as BatchJobResult;
  return {
    ...result,
    chapter_results: Array.isArray(result.chapter_results) ? result.chapter_results : [],
    failed_chapters: Array.isArray(result.failed_chapters) ? result.failed_chapters : [],
  };
}

function jobStorageKey(projectId: string) {
  return `batch:lastJob:v1:${projectId}`;
}

function loadSavedJobId(projectId: string): string | null {
  try {
    return localStorage.getItem(jobStorageKey(projectId));
  } catch {
    return null;
  }
}

function saveJobId(projectId: string, nextJobId: string) {
  try {
    localStorage.setItem(jobStorageKey(projectId), nextJobId);
  } catch {
    // localStorage can be disabled in private browsing; polling still works in memory.
  }
}

export function BatchPage() {
  const { projectId = "" } = useParams();
  const { message } = App.useApp();
  const [form] = Form.useForm<{ chapter_start: number; chapter_end: number }>();
  const [job, setJob] = useState<GenerationJob | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [manualJobId, setManualJobId] = useState("");

  const chaptersQuery = useQuery({
    queryKey: ["project-chapters", projectId],
    queryFn: () => studioApi.listChapters(projectId),
    enabled: Boolean(projectId),
  });

  const chapters = useMemo(() => {
    return [...(chaptersQuery.data?.chapters ?? [])].sort((left, right) => left.chapter_no - right.chapter_no);
  }, [chaptersQuery.data?.chapters]);
  const firstChapterNo = chapters[0]?.chapter_no;
  const lastChapterNo = chapters[chapters.length - 1]?.chapter_no;
  const hasChapters = firstChapterNo !== undefined && lastChapterNo !== undefined;

  useEffect(() => {
    if (!projectId) return;
    const savedJobId = loadSavedJobId(projectId);
    setJobId(savedJobId);
    setJob(null);
  }, [projectId]);

  useEffect(() => {
    if (!hasChapters) return;
    form.setFieldsValue({ chapter_start: firstChapterNo, chapter_end: lastChapterNo });
  }, [firstChapterNo, form, hasChapters, lastChapterNo]);

  const jobQuery = useQuery({
    queryKey: ["generation-job", jobId],
    queryFn: () => studioApi.getJob(jobId || ""),
    enabled: Boolean(jobId),
    refetchInterval: job && activeStatuses.has(job.status) ? 2000 : false,
  });

  const recentJobsQuery = useQuery({
    queryKey: ["recent-batch-jobs", projectId],
    queryFn: () => studioApi.listJobs({ project_id: projectId, job_type: "batch_generate", limit: 8 }),
    enabled: Boolean(projectId),
    refetchInterval: job && activeStatuses.has(job.status) ? 5000 : false,
  });

  useEffect(() => {
    if (jobQuery.data?.job) {
      setJob(jobQuery.data.job);
    }
  }, [jobQuery.data?.job]);

  const mutation = useMutation({
    mutationFn: (values: { chapter_start: number; chapter_end: number }) => studioApi.batchGenerate(projectId, values.chapter_start, values.chapter_end),
    onSuccess: (result) => {
      setJob(result.job);
      setJobId(result.job.id);
      saveJobId(projectId, result.job.id);
      recentJobsQuery.refetch();
      message.success("批量任务已创建，后台将逐章生成正文");
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "批量生成失败"),
  });

  const controlMutation = useMutation({
    mutationFn: ({ action, jobId: targetJobId }: { action: "pause" | "resume" | "cancel"; jobId: string }) => {
      if (action === "pause") return studioApi.pauseJob(targetJobId, "从批量监控页暂停");
      if (action === "resume") return studioApi.resumeJob(targetJobId, "从批量监控页恢复");
      return studioApi.cancelJob(targetJobId, "从批量监控页取消");
    },
    onSuccess: ({ job: nextJob }, variables) => {
      setJob(nextJob);
      setJobId(nextJob.id);
      saveJobId(projectId, nextJob.id);
      recentJobsQuery.refetch();
      const labels = { pause: "任务已暂停", resume: "任务已恢复", cancel: "任务已取消" };
      message.success(labels[variables.action]);
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "任务状态更新失败"),
  });

  const retryMutation = useMutation({
    mutationFn: (targetJobId: string) => studioApi.retryJob(targetJobId),
    onSuccess: ({ job: nextJob }) => {
      setJob(nextJob);
      setJobId(nextJob.id);
      saveJobId(projectId, nextJob.id);
      recentJobsQuery.refetch();
      message.success("批量任务已重新入队");
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "任务重试失败"),
  });

  const batchResult = asBatchResult(job?.result);
  const completedChapters = batchResult.chapter_results ?? [];
  const failedChapters = batchResult.failed_chapters ?? [];
  const totalSteps = Math.max(job?.progress.total_steps ?? 0, 1);
  const completedSteps = job?.progress.completed_steps ?? completedChapters.length;
  const percent = job?.status === "succeeded" ? 100 : Math.round((completedSteps / totalSteps) * 100);
  const childTotalSteps = job?.progress.child_total_steps ?? 0;
  const childCompletedSteps = job?.progress.child_completed_steps ?? 0;
  const childPercent = childTotalSteps > 0 ? Math.round((childCompletedSteps / childTotalSteps) * 100) : 0;
  const canPause = Boolean(job && activeStatuses.has(job.status));
  const canResume = job?.status === "paused";
  const canCancel = Boolean(job && !terminalStatuses.has(job.status));
  const canRetry = Boolean(job && (job.status === "failed" || job.status === "cancelled"));
  const isBusy = mutation.isPending || controlMutation.isPending || retryMutation.isPending;

  const control = (action: "pause" | "resume" | "cancel") => {
    if (job) controlMutation.mutate({ action, jobId: job.id });
  };

  const attachJob = (nextJobId: string, nextJob?: GenerationJob) => {
    const normalized = nextJobId.trim();
    if (!normalized) return;
    setJob(nextJob ?? null);
    setJobId(normalized);
    saveJobId(projectId, normalized);
  };

  return (
    <Space direction="vertical" size={18} className="page-stack">
      <div className="page-heading">
        <div>
          <Typography.Title level={2}>批量生成与监控</Typography.Title>
          <Typography.Text type="secondary">选择已确认章节范围，系统会创建可恢复任务并逐章提交正文与正典更新。</Typography.Text>
        </div>
      </div>

      {!hasChapters ? (
        <Alert
          type="warning"
          showIcon
          message="请先确认章纲"
          description="批量正文生成只处理已经存在的章节。请先在大纲中确认章纲或手动创建章节，再启动长篇批量生成。"
        />
      ) : null}

      <Card>
        <Form layout="inline" form={form} onFinish={(values) => mutation.mutate(values)}>
          <Form.Item name="chapter_start" label="起始章节" rules={[{ required: true, message: "请输入起始章节" }]}>
            <InputNumber min={firstChapterNo ?? 1} max={lastChapterNo} disabled={!hasChapters || isBusy} />
          </Form.Item>
          <Form.Item
            name="chapter_end"
            label="结束章节"
            dependencies={["chapter_start"]}
            rules={[
              { required: true, message: "请输入结束章节" },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value) return Promise.resolve();
                  if (value < getFieldValue("chapter_start")) return Promise.reject(new Error("结束章节不能小于起始章节"));
                  if (lastChapterNo !== undefined && value > lastChapterNo) return Promise.reject(new Error("结束章节不能超过已确认章节范围"));
                  return Promise.resolve();
                },
              }),
            ]}
          >
            <InputNumber min={firstChapterNo ?? 1} max={lastChapterNo} disabled={!hasChapters || isBusy} />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={mutation.isPending} disabled={!hasChapters || controlMutation.isPending || retryMutation.isPending}>
            创建批量任务
          </Button>
        </Form>
        {hasChapters ? (
          <Typography.Text type="secondary">
            当前可生成章节：第{firstChapterNo}章至第{lastChapterNo}章，共 {chapters.length} 章。
          </Typography.Text>
        ) : null}
      </Card>

      {mutation.error ? <Alert type="error" message="批量生成失败" description={mutation.error instanceof Error ? mutation.error.message : undefined} showIcon /> : null}

      <Card title="恢复任务">
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          <Input.Search
            placeholder="输入已有 job id"
            enterButton="读取任务"
            value={manualJobId}
            onChange={(event) => setManualJobId(event.target.value)}
            onSearch={(value) => attachJob(value)}
          />
          <List
            size="small"
            loading={recentJobsQuery.isLoading}
            dataSource={recentJobsQuery.data?.jobs ?? []}
            locale={{ emptyText: "暂无最近批量任务" }}
            renderItem={(item) => {
              const result = asBatchResult(item.result);
              const range = result.requested_range;
              return (
                <List.Item actions={[<Button key="open" type="link" onClick={() => attachJob(item.id, item)}>打开</Button>]}>
                  <List.Item.Meta
                    title={
                      <Space wrap>
                        <Typography.Text code>{item.id}</Typography.Text>
                        <Tag color={item.status === "succeeded" ? "success" : item.status === "failed" || item.status === "cancelled" ? "error" : "processing"}>
                          {item.status}
                        </Tag>
                      </Space>
                    }
                    description={[
                      range?.chapter_start && range?.chapter_end ? `章节：第${range.chapter_start}章至第${range.chapter_end}章` : "",
                      item.progress?.message || "",
                      `创建：${item.created_at}`,
                    ].filter(Boolean).join(" · ")}
                  />
                </List.Item>
              );
            }}
          />
        </Space>
      </Card>

      <Card
        title="任务进度"
        extra={job ? <Tag color={job.status === "succeeded" ? "success" : job.status === "cancelled" || job.status === "failed" ? "error" : "processing"}>{job.status}</Tag> : null}
      >
        <Progress percent={percent} status={job?.status === "failed" ? "exception" : activeStatuses.has(job?.status ?? "") ? "active" : undefined} />
        <Space direction="vertical" size={6} style={{ width: "100%", marginBottom: 12 }}>
          <Typography.Text type="secondary">{job?.progress.message || (jobId ? "正在读取任务状态..." : "尚未创建批量任务")}</Typography.Text>
          {job?.progress.current_chapter_no ? (
            <Typography.Text type="secondary">当前章节：第{job.progress.current_chapter_no}章</Typography.Text>
          ) : null}
          {job?.progress.child_current_step ? (
            <Space direction="vertical" size={4} style={{ width: "100%" }}>
              <Typography.Text type="secondary">
                当前 Agent：{job.progress.child_current_step}（{childCompletedSteps}/{childTotalSteps || "?"}）
              </Typography.Text>
              <Progress percent={childPercent} size="small" status={activeStatuses.has(job?.status ?? "") ? "active" : undefined} />
            </Space>
          ) : null}
          {job?.error?.message ? <Alert type="error" showIcon message={job.error.message} /> : null}
        </Space>
        <Space wrap style={{ marginBottom: 12 }}>
          <Button disabled={!canPause || isBusy} loading={controlMutation.isPending} onClick={() => control("pause")}>暂停</Button>
          <Button disabled={!canResume || isBusy} loading={controlMutation.isPending} onClick={() => control("resume")}>恢复</Button>
          <Button danger disabled={!canCancel || isBusy} loading={controlMutation.isPending} onClick={() => control("cancel")}>取消</Button>
          <Button disabled={!canRetry || isBusy} loading={retryMutation.isPending} onClick={() => job && retryMutation.mutate(job.id)}>重试</Button>
        </Space>

        <List
          header={<Typography.Text strong>已完成章节</Typography.Text>}
          dataSource={completedChapters}
          locale={{ emptyText: job ? "任务创建后会逐章显示完成结果" : "尚未创建批量任务" }}
          renderItem={(item) => (
            <List.Item>
              第{item.chapter_no}章 {item.title || item.chapter?.title}
              <Typography.Text type="secondary"> {item.status || item.chapter?.status} · {item.word_count ?? item.chapter?.word_count ?? 0} 字</Typography.Text>
            </List.Item>
          )}
        />

        <List
          header={<Typography.Text strong>失败章节</Typography.Text>}
          dataSource={failedChapters}
          locale={{ emptyText: "暂无失败章节" }}
          renderItem={(item) => (
            <List.Item>
              第{item.chapter_no}章
              <Typography.Text type="danger"> {item.message}</Typography.Text>
            </List.Item>
          )}
        />
      </Card>
    </Space>
  );
}
