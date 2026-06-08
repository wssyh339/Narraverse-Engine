import { AlertTriangle, CheckCircle2, CircleDashed } from "lucide-react";
import type { GenerationJob } from "../types/api";

export function JobStatusPanel({ job }: { job: GenerationJob }) {
  const isDone = ["succeeded", "failed", "cancelled"].includes(job.status);
  const Icon = job.status === "failed" ? AlertTriangle : isDone ? CheckCircle2 : CircleDashed;

  return (
    <section className="panel compact-panel">
      <div className="section-title">
        <Icon size={18} />
        <h2>任务状态</h2>
      </div>
      <dl className="detail-grid">
        <div>
          <dt>任务 ID</dt>
          <dd>{job.id}</dd>
        </div>
        <div>
          <dt>状态</dt>
          <dd>{job.status}</dd>
        </div>
        <div>
          <dt>模型</dt>
          <dd>{job.model}</dd>
        </div>
        <div>
          <dt>进度</dt>
          <dd>{job.progress.message ?? job.progress.current_step ?? "暂无进度消息"}</dd>
        </div>
      </dl>
    </section>
  );
}
