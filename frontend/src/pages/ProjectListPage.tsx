import { useMutation } from "@tanstack/react-query";
import { AlertCircle, Check, FilePlus2, Loader2 } from "lucide-react";
import type { ChangeEvent, FormEvent } from "react";
import { useMemo, useState } from "react";
import { z } from "zod";
import { navigateTo } from "../App";
import { createProject, type CreateProjectInput } from "../api/projects";
import { ApiClientError, isApiClientError } from "../api/client";
import { saveProjectSnapshot } from "../stores/editorStore";

const createProjectSchema = z.object({
  title: z.string().min(1, "请输入项目名称").max(120, "项目名称不能超过 120 字"),
  genre: z.string().min(1, "请输入题材").max(60, "题材不能超过 60 字"),
  target_reader: z.string().min(1, "请输入目标读者"),
  premise: z.string().min(1, "请输入一句话设定"),
  style_guide: z.string(),
  language: z.string().min(1, "请输入语言代码"),
  planned_chapter_count: z.number().int("章节数必须是整数").positive("章节数必须大于 0"),
  chapter_word_target: z.number().int("字数目标必须是整数").min(500, "单章字数至少 500").max(10000, "单章字数最多 10000"),
});

type FieldErrors = Partial<Record<keyof CreateProjectInput, string>>;

const initialForm: CreateProjectInput = {
  title: "",
  genre: "",
  target_reader: "",
  premise: "",
  style_guide: "",
  language: "zh-CN",
  planned_chapter_count: 80,
  chapter_word_target: 3000,
};

function getApiErrorMessage(error: unknown): string {
  if (isApiClientError(error)) {
    return `${error.message}${error.requestId ? `（${error.requestId}）` : ""}`;
  }
  return "创建失败，请稍后重试。";
}

function collectServerFieldErrors(error: unknown): string[] {
  if (!(error instanceof ApiClientError)) {
    return [];
  }
  const details = error.details as { errors?: Array<{ loc?: unknown[]; msg?: string }> };
  if (!Array.isArray(details.errors)) {
    return [];
  }
  return details.errors.map((item) => {
    const field = item.loc?.slice(-1)[0];
    return `${String(field ?? "字段")}：${item.msg ?? "不合法"}`;
  });
}

export function ProjectListPage() {
  const [form, setForm] = useState<CreateProjectInput>(initialForm);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});

  const mutation = useMutation({
    mutationFn: createProject,
    onSuccess: (snapshot) => {
      saveProjectSnapshot(snapshot);
      navigateTo(`/projects/${snapshot.project.id}/workspace`);
    },
  });

  const serverFieldErrors = useMemo(() => collectServerFieldErrors(mutation.error), [mutation.error]);

  function updateField<TField extends keyof CreateProjectInput>(field: TField, value: CreateProjectInput[TField]) {
    setForm((current) => ({ ...current, [field]: value }));
    setFieldErrors((current) => ({ ...current, [field]: undefined }));
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsed = createProjectSchema.safeParse(form);
    if (!parsed.success) {
      const nextErrors: FieldErrors = {};
      for (const issue of parsed.error.issues) {
        const field = issue.path[0] as keyof CreateProjectInput;
        nextErrors[field] = issue.message;
      }
      setFieldErrors(nextErrors);
      return;
    }
    mutation.mutate(parsed.data);
  }

  return (
    <div className="page-grid">
      <section className="panel">
        <p className="eyebrow">/projects/new</p>
        <div className="title-row">
          <div>
            <h1>新建长篇项目</h1>
            <p className="lede">创建项目后，后端会同时初始化一份空的故事圣经。</p>
          </div>
          <FilePlus2 className="title-icon" size={28} />
        </div>

        <form className="form-stack" onSubmit={handleSubmit}>
          <label>
            <span>项目名称</span>
            <input
              value={form.title}
              onChange={(event: ChangeEvent<HTMLInputElement>) => updateField("title", event.target.value)}
              placeholder="星海遗民"
            />
            {fieldErrors.title ? <small className="field-error">{fieldErrors.title}</small> : null}
          </label>

          <div className="form-grid">
            <label>
              <span>题材</span>
              <input
                value={form.genre}
                onChange={(event: ChangeEvent<HTMLInputElement>) => updateField("genre", event.target.value)}
                placeholder="科幻"
              />
              {fieldErrors.genre ? <small className="field-error">{fieldErrors.genre}</small> : null}
            </label>
            <label>
              <span>语言</span>
              <input
                value={form.language}
                onChange={(event: ChangeEvent<HTMLInputElement>) => updateField("language", event.target.value)}
                placeholder="zh-CN"
              />
              {fieldErrors.language ? <small className="field-error">{fieldErrors.language}</small> : null}
            </label>
          </div>

          <label>
            <span>目标读者</span>
            <textarea
              value={form.target_reader}
              onChange={(event: ChangeEvent<HTMLTextAreaElement>) => updateField("target_reader", event.target.value)}
              placeholder="喜欢群像、文明冲突和长期伏笔的中文网文读者"
              rows={3}
            />
            {fieldErrors.target_reader ? <small className="field-error">{fieldErrors.target_reader}</small> : null}
          </label>

          <label>
            <span>一句话设定</span>
            <textarea
              value={form.premise}
              onChange={(event: ChangeEvent<HTMLTextAreaElement>) => updateField("premise", event.target.value)}
              placeholder="一名失忆舰长在废弃星门中醒来..."
              rows={4}
            />
            {fieldErrors.premise ? <small className="field-error">{fieldErrors.premise}</small> : null}
          </label>

          <label>
            <span>风格约束</span>
            <textarea
              value={form.style_guide}
              onChange={(event: ChangeEvent<HTMLTextAreaElement>) => updateField("style_guide", event.target.value)}
              placeholder="第三人称有限视角，节奏偏紧，避免过度解释设定。"
              rows={3}
            />
          </label>

          <div className="form-grid">
            <label>
              <span>计划章节数</span>
              <input
                type="number"
                min={1}
                value={form.planned_chapter_count}
                onChange={(event: ChangeEvent<HTMLInputElement>) => updateField("planned_chapter_count", Number(event.target.value))}
              />
              {fieldErrors.planned_chapter_count ? <small className="field-error">{fieldErrors.planned_chapter_count}</small> : null}
            </label>
            <label>
              <span>单章字数目标</span>
              <input
                type="number"
                min={500}
                max={10000}
                value={form.chapter_word_target}
                onChange={(event: ChangeEvent<HTMLInputElement>) => updateField("chapter_word_target", Number(event.target.value))}
              />
              {fieldErrors.chapter_word_target ? <small className="field-error">{fieldErrors.chapter_word_target}</small> : null}
            </label>
          </div>

          {mutation.error ? (
            <div className="error-block" role="alert">
              <AlertCircle size={18} />
              <div>
                <strong>创建失败</strong>
                <span>{getApiErrorMessage(mutation.error)}</span>
                {serverFieldErrors.length > 0 ? (
                  <ul>
                    {serverFieldErrors.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                ) : null}
              </div>
            </div>
          ) : null}

          {mutation.isPending ? (
            <div className="loading-block" aria-live="polite">
              <Loader2 size={18} />
              <span>正在创建项目并初始化故事圣经...</span>
            </div>
          ) : null}

          <button className="primary-button" type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? <Loader2 size={18} /> : <Check size={18} />}
            <span>{mutation.isPending ? "创建中" : "创建项目"}</span>
          </button>
        </form>
      </section>

      <aside className="panel side-panel">
        <p className="eyebrow">响应结果</p>
        {mutation.isPending ? (
          <div className="skeleton-stack" aria-label="加载中">
            <span />
            <span />
            <span />
          </div>
        ) : mutation.data ? (
          <div className="success-block">
            <Check size={18} />
            <div>
              <strong>项目已创建</strong>
              <span>{mutation.data.project.title}</span>
              <code>{mutation.data.project.id}</code>
              <span>故事圣经版本：v{mutation.data.story_bible.version}</span>
            </div>
          </div>
        ) : mutation.error ? (
          <div className="empty-block error-empty">
            <strong>无法展示项目</strong>
            <span>后端没有返回可用的项目数据，请修正错误后重新提交。</span>
          </div>
        ) : (
          <div className="empty-block">
            <strong>还没有创建项目</strong>
            <span>提交表单后，这里会展示后端返回的项目 ID 和故事圣经版本。</span>
          </div>
        )}
      </aside>
    </div>
  );
}
