import { useQuery } from "@tanstack/react-query";
import { AlertCircle, Clock3, Loader2, RefreshCw } from "lucide-react";
import { getJob } from "../api/jobs";
import { isApiClientError } from "../api/client";
import { JobStatusPanel } from "../components/JobStatusPanel";
import type { GenerationJob } from "../types/api";

interface JobDetailPageProps {
  jobId: string;
}

const terminalStatuses = new Set(["succeeded", "failed", "cancelled"]);

function errorText(error: unknown): string {
  if (isApiClientError(error)) {
    return `${error.message}${error.requestId ? `（${error.requestId}）` : ""}`;
  }
  return "任务详情读取失败，请稍后重试。";
}

function JsonBlock({ value }: { value: unknown }) {
  return <pre className="json-box">{value === null ? "null" : JSON.stringify(value, null, 2)}</pre>;
}

function JobFields({ job }: { job: GenerationJob }) {
  const progress = job.progress;
  const total = progress.total_steps ?? 0;
  const completed = progress.completed_steps ?? 0;
  const percent = total > 0 ? Math.round((completed / total) * 100) : 0;

  return (
    <div className="job-detail-grid">
      <JobStatusPanel job={job} />

      <section className="panel compact-panel">
        <div className="section-title">
          <Clock3 size={18} />
          <h2>基础信息</h2>
        </div>
        <dl className="detail-grid">
          <div>
            <dt>任务 ID</dt>
            <dd>{job.id}</dd>
          </div>
          <div>
            <dt>项目 ID</dt>
            <dd>{job.project_id}</dd>
          </div>
          <div>
            <dt>章节 ID</dt>
            <dd>{job.chapter_id ?? "无"}</dd>
          </div>
          <div>
            <dt>任务类型</dt>
            <dd>{job.job_type}</dd>
          </div>
          <div>
            <dt>幂等键</dt>
            <dd>{job.idempotency_key}</dd>
          </div>
          <div>
            <dt>创建时间</dt>
            <dd>{job.created_at}</dd>
          </div>
          <div>
            <dt>开始时间</dt>
            <dd>{job.started_at ?? "未开始"}</dd>
          </div>
          <div>
            <dt>结束时间</dt>
            <dd>{job.finished_at ?? "未结束"}</dd>
          </div>
        </dl>
      </section>

      <section className="panel compact-panel">
        <div className="section-title">
          <RefreshCw size={18} />
          <h2>进度</h2>
        </div>
        <div className="progress-track" aria-label="任务进度">
          <span style={{ width: `${percent}%` }} />
        </div>
        <dl className="detail-grid">
          <div>
            <dt>当前步骤</dt>
            <dd>{progress.current_step ?? "未知"}</dd>
          </div>
          <div>
            <dt>步骤数</dt>
            <dd>
              {completed} / {total || "?"}
            </dd>
          </div>
          <div>
            <dt>消息</dt>
            <dd>{progress.message ?? "暂无进度消息"}</dd>
          </div>
        </dl>
      </section>

      <section className="panel compact-panel">
        <div className="section-title">
          <h2>结果</h2>
        </div>
        {job.result === null ? (
          <div className="empty-block">
            <strong>暂无生成结果</strong>
            <span>任务仍在等待或运行时，后端会返回 `result: null`。</span>
          </div>
        ) : (
          <JsonBlock value={job.result} />
        )}
      </section>

      <section className="panel compact-panel">
        <div className="section-title">
          <h2>错误</h2>
        </div>
        {job.error ? (
          <div className="error-block">
            <AlertCircle size={18} />
            <div>
              <strong>任务失败</strong>
              <span>{job.error.message}</span>
            </div>
          </div>
        ) : (
          <div className="empty-block">
            <strong>暂无任务错误</strong>
            <span>后端返回 `error: null`。</span>
          </div>
        )}
      </section>
    </div>
  );
}

export function JobDetailPage({ jobId }: JobDetailPageProps) {
  const query = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => getJob(jobId),
    refetchInterval: (queryInfo) => {
      const data = queryInfo.state.data as { job: GenerationJob } | undefined;
      if (!data) {
        return false;
      }
      return terminalStatuses.has(data.job.status) ? false : 2000;
    },
  });

  return (
    <div className="job-page">
      <section className="panel">
        <p className="eyebrow">/jobs/:jobId</p>
        <div className="title-row">
          <div>
            <h1>任务详情</h1>
            <p className="lede">查看后端任务状态、进度、结果和错误信息。</p>
          </div>
          <span className="status-pill">{query.data?.job.status ?? "loading"}</span>
        </div>

        {query.isLoading ? (
          <div className="loading-block">
            <Loader2 size={18} />
            <span>正在读取任务详情...</span>
          </div>
        ) : null}

        {query.error ? (
          <div className="error-block" role="alert">
            <AlertCircle size={18} />
            <div>
              <strong>无法读取任务</strong>
              <span>{errorText(query.error)}</span>
            </div>
          </div>
        ) : null}

        {!query.isLoading && !query.error && !query.data ? (
          <div className="empty-block">
            <strong>暂无任务数据</strong>
            <span>后端没有返回可展示的任务详情。</span>
          </div>
        ) : null}
      </section>

      {query.data ? (
        <JobFields job={query.data.job} />
      ) : null}
    </div>
  );
}
