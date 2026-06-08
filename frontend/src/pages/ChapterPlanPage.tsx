import { useMutation } from "@tanstack/react-query";
import { AlertCircle, Check, ListChecks, Loader2, TriangleAlert } from "lucide-react";
import type { ChangeEvent, FormEvent } from "react";
import { useEffect, useMemo, useState } from "react";
import { z } from "zod";
import { navigateTo } from "../App";
import { planChapters, type PlanChaptersInput } from "../api/chapters";
import { isApiClientError } from "../api/client";
import { ProjectNav } from "../components/ProjectNav";
import { readProjectSnapshotFor } from "../stores/editorStore";
import type { GenerationJob, ProjectSnapshot } from "../types/api";

interface ChapterPlanPageProps {
  projectId: string;
}

interface ChapterPlanForm {
  volume_title: string;
  start_chapter_no: number;
  chapter_count: number;
  outline_requirement: string;
  overwrite_existing: boolean;
  model: string;
}

const chapterPlanSchema = z.object({
  volume_title: z.string().min(1, "请输入分卷标题"),
  start_chapter_no: z.number().int().min(1, "起始章节号必须大于 0"),
  chapter_count: z.number().int().min(1, "章节数至少为 1").max(100, "章节数最多 100"),
  outline_requirement: z.string().min(1, "请输入规划要求"),
  overwrite_existing: z.boolean(),
  model: z.string().min(1, "请选择模型"),
});

const initialForm: ChapterPlanForm = {
  volume_title: "第一卷：失落星门",
  start_chapter_no: 1,
  chapter_count: 10,
  outline_requirement: "",
  overwrite_existing: false,
  model: "qwen-plus",
};

function buildIdempotencyKey(projectId: string, form: ChapterPlanForm): string {
  const endChapter = form.start_chapter_no + form.chapter_count - 1;
  const volume = form.volume_title.trim().replace(/\s+/g, "-") || "volume";
  return `plan:${projectId}:${volume}:chapters-${form.start_chapter_no}-${endChapter}:v1`;
}

function apiErrorText(error: unknown): string {
  if (isApiClientError(error)) {
    return `${error.message}${error.requestId ? `（${error.requestId}）` : ""}`;
  }
  return "章节规划任务创建失败，请稍后重试。";
}

export function ChapterPlanPage({ projectId }: ChapterPlanPageProps) {
  const [isLoading, setIsLoading] = useState(true);
  const [snapshot, setSnapshot] = useState<ProjectSnapshot | null>(null);
  const [form, setForm] = useState<ChapterPlanForm>(initialForm);
  const [fieldError, setFieldError] = useState<string>("");
  const [createdJob, setCreatedJob] = useState<GenerationJob | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSnapshot(readProjectSnapshotFor(projectId));
      setIsLoading(false);
    }, 120);
    return () => window.clearTimeout(timer);
  }, [projectId]);

  const idempotencyKey = useMemo(() => buildIdempotencyKey(projectId, form), [projectId, form]);

  const mutation = useMutation({
    mutationFn: (input: PlanChaptersInput) => planChapters(projectId, input),
    onSuccess: ({ job }) => {
      setCreatedJob(job);
      window.setTimeout(() => navigateTo(`/jobs/${job.id}`), 350);
    },
  });

  function updateField<TField extends keyof ChapterPlanForm>(field: TField, value: ChapterPlanForm[TField]) {
    setFieldError("");
    setCreatedJob(null);
    setForm((current) => ({ ...current, [field]: value }));
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsed = chapterPlanSchema.safeParse(form);
    if (!parsed.success) {
      setFieldError(parsed.error.issues[0]?.message ?? "表单字段不合法");
      return;
    }
    mutation.mutate({
      ...parsed.data,
      idempotency_key: idempotencyKey,
      model: parsed.data.model,
    });
  }

  if (isLoading) {
    return (
      <section className="panel">
        <ProjectNav projectId={projectId} title="章节规划" />
        <div className="loading-block">
          <Loader2 size={18} />
          <span>正在读取项目上下文...</span>
        </div>
      </section>
    );
  }

  if (!snapshot) {
    return (
      <section className="panel">
        <ProjectNav title="章节规划" />
        <div className="error-block" role="alert">
          <TriangleAlert size={18} />
          <div>
            <strong>无法创建章节规划</strong>
            <span>请先创建项目，后端 MVP 暂未提供项目详情查询接口。</span>
          </div>
        </div>
        <div className="empty-block">
          <strong>暂无项目上下文</strong>
          <span>创建项目并完成故事圣经后，再规划章节范围。</span>
        </div>
      </section>
    );
  }

  return (
    <div className="page-grid">
      <section className="panel">
        <ProjectNav projectId={projectId} title="章节规划" />
        <p className="eyebrow">/projects/:projectId/chapters/plan</p>
        <div className="title-row">
          <div>
            <h1>{snapshot.project.title}</h1>
            <p className="lede">提交后会创建章节规划任务，并跳转到任务详情页轮询状态。</p>
          </div>
          <ListChecks className="title-icon" size={28} />
        </div>

        <form className="form-stack" onSubmit={handleSubmit}>
          <label>
            <span>分卷标题</span>
            <input
              value={form.volume_title}
              onChange={(event: ChangeEvent<HTMLInputElement>) => updateField("volume_title", event.target.value)}
            />
          </label>
          <div className="form-grid">
            <label>
              <span>起始章节号</span>
              <input
                type="number"
                min={1}
                value={form.start_chapter_no}
                onChange={(event: ChangeEvent<HTMLInputElement>) => updateField("start_chapter_no", Number(event.target.value))}
              />
            </label>
            <label>
              <span>章节数</span>
              <input
                type="number"
                min={1}
                max={100}
                value={form.chapter_count}
                onChange={(event: ChangeEvent<HTMLInputElement>) => updateField("chapter_count", Number(event.target.value))}
              />
            </label>
          </div>
          <label>
            <span>规划要求</span>
            <textarea
              value={form.outline_requirement}
              onChange={(event: ChangeEvent<HTMLTextAreaElement>) => updateField("outline_requirement", event.target.value)}
              rows={5}
              placeholder="建立主角身份谜团、星门遗迹、第一位主要反派和舰队内部矛盾。"
            />
          </label>
          <div className="form-grid">
            <label>
              <span>模型</span>
              <select value={form.model} onChange={(event: ChangeEvent<HTMLSelectElement>) => updateField("model", event.target.value)}>
                <option value="qwen-plus">qwen-plus</option>
                <option value="deepseek-v4-flash">deepseek-v4-flash</option>
                <option value="deepseek-v4-pro">deepseek-v4-pro</option>
              </select>
            </label>
            <label>
              <span>幂等键</span>
              <input className="readonly-input" value={idempotencyKey} readOnly />
            </label>
          </div>
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={form.overwrite_existing}
              onChange={(event: ChangeEvent<HTMLInputElement>) => updateField("overwrite_existing", event.target.checked)}
            />
            <span>覆盖已存在章节范围</span>
          </label>

          {fieldError ? (
            <div className="error-block" role="alert">
              <AlertCircle size={18} />
              <div>
                <strong>表单不完整</strong>
                <span>{fieldError}</span>
              </div>
            </div>
          ) : null}

          {mutation.error ? (
            <div className="error-block" role="alert">
              <AlertCircle size={18} />
              <div>
                <strong>任务创建失败</strong>
                <span>{apiErrorText(mutation.error)}</span>
              </div>
            </div>
          ) : null}

          {mutation.isPending ? (
            <div className="loading-block">
              <Loader2 size={18} />
              <span>正在创建章节规划任务...</span>
            </div>
          ) : null}

          <button className="primary-button" type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? <Loader2 size={18} /> : <Check size={18} />}
            <span>{mutation.isPending ? "提交中" : "创建规划任务"}</span>
          </button>
        </form>
      </section>

      <aside className="panel side-panel">
        <p className="eyebrow">任务预览</p>
        {mutation.isPending ? (
          <div className="skeleton-stack" aria-label="加载中">
            <span />
            <span />
            <span />
          </div>
        ) : createdJob ? (
          <div className="success-block">
            <Check size={18} />
            <div>
              <strong>任务已创建</strong>
              <span>{createdJob.status}</span>
              <code>{createdJob.id}</code>
              <span>{createdJob.progress.message ?? "准备进入任务详情页"}</span>
            </div>
          </div>
        ) : (
          <div className="empty-block">
            <strong>还没有规划任务</strong>
            <span>提交表单后，这里会展示后端返回的 job ID 和初始状态。</span>
          </div>
        )}
      </aside>
    </div>
  );
}
