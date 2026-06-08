import { useMutation } from "@tanstack/react-query";
import { AlertCircle, Check, ClipboardList, Loader2, TriangleAlert } from "lucide-react";
import type { ChangeEvent, FormEvent } from "react";
import { useEffect, useState } from "react";
import { z } from "zod";
import { updateStoryBible, type UpdateStoryBibleInput } from "../api/projects";
import { isApiClientError } from "../api/client";
import { ProjectNav } from "../components/ProjectNav";
import { readProjectSnapshotFor, updateStoredStoryBible } from "../stores/editorStore";
import type { ProjectSnapshot } from "../types/api";

interface StoryBiblePageProps {
  projectId: string;
}

interface StoryBibleForm {
  world_setting: string;
  main_conflict: string;
  themes: string;
  style_guide: string;
  narrative_pov: UpdateStoryBibleInput["narrative_pov"];
  forbidden_elements: string;
  continuity_rules: string;
}

const storyBibleSchema = z.object({
  world_setting: z.string(),
  main_conflict: z.string(),
  themes: z.array(z.string()),
  style_guide: z.string(),
  narrative_pov: z.enum(["first_person", "third_person_limited", "third_person_omniscient"]),
  forbidden_elements: z.array(z.string()),
  continuity_rules: z.array(z.string()),
});

function listToText(values: string[]): string {
  return values.join("\n");
}

function textToList(value: string): string[] {
  return value
    .split(/\n|，|,/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function formFromSnapshot(snapshot: ProjectSnapshot): StoryBibleForm {
  const storyBible = snapshot.story_bible;
  return {
    world_setting: storyBible.world_setting,
    main_conflict: storyBible.main_conflict,
    themes: listToText(storyBible.themes),
    style_guide: storyBible.style_guide ?? snapshot.project.style_guide,
    narrative_pov: storyBible.narrative_pov,
    forbidden_elements: listToText(storyBible.forbidden_elements),
    continuity_rules: listToText(storyBible.continuity_rules),
  };
}

function apiErrorText(error: unknown): string {
  if (isApiClientError(error)) {
    return `${error.message}${error.requestId ? `（${error.requestId}）` : ""}`;
  }
  return "故事圣经更新失败，请稍后重试。";
}

export function StoryBiblePage({ projectId }: StoryBiblePageProps) {
  const [isLoading, setIsLoading] = useState(true);
  const [snapshot, setSnapshot] = useState<ProjectSnapshot | null>(null);
  const [form, setForm] = useState<StoryBibleForm>({
    world_setting: "",
    main_conflict: "",
    themes: "",
    style_guide: "",
    narrative_pov: "third_person_limited",
    forbidden_elements: "",
    continuity_rules: "",
  });

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const current = readProjectSnapshotFor(projectId);
      setSnapshot(current);
      if (current) {
        setForm(formFromSnapshot(current));
      }
      setIsLoading(false);
    }, 120);
    return () => window.clearTimeout(timer);
  }, [projectId]);

  const mutation = useMutation({
    mutationFn: (input: UpdateStoryBibleInput) => updateStoryBible(projectId, input),
    onSuccess: ({ story_bible }) => {
      const next = updateStoredStoryBible(story_bible);
      if (next) {
        setSnapshot(next);
        setForm(formFromSnapshot(next));
      }
    },
  });

  function updateField<TField extends keyof StoryBibleForm>(field: TField, value: StoryBibleForm[TField]) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const input = storyBibleSchema.parse({
      world_setting: form.world_setting,
      main_conflict: form.main_conflict,
      themes: textToList(form.themes),
      style_guide: form.style_guide,
      narrative_pov: form.narrative_pov,
      forbidden_elements: textToList(form.forbidden_elements),
      continuity_rules: textToList(form.continuity_rules),
    });
    mutation.mutate(input);
  }

  if (isLoading) {
    return (
      <section className="panel">
        <ProjectNav projectId={projectId} title="故事圣经" />
        <div className="loading-block">
          <Loader2 size={18} />
          <span>正在读取故事圣经...</span>
        </div>
      </section>
    );
  }

  if (!snapshot) {
    return (
      <section className="panel">
        <ProjectNav title="故事圣经" />
        <div className="error-block" role="alert">
          <TriangleAlert size={18} />
          <div>
            <strong>无法载入故事圣经</strong>
            <span>请先创建项目，后端 MVP 暂未提供项目详情查询接口。</span>
          </div>
        </div>
        <div className="empty-block">
          <strong>暂无故事圣经数据</strong>
          <span>创建项目后会自动生成一份空故事圣经，再回到这里编辑。</span>
        </div>
      </section>
    );
  }

  return (
    <div className="page-grid">
      <section className="panel">
        <ProjectNav projectId={projectId} title="故事圣经" />
        <p className="eyebrow">/projects/:projectId/story-bible</p>
        <div className="title-row">
          <div>
            <h1>{snapshot.project.title}</h1>
            <p className="lede">维护世界观、主冲突、主题、叙事视角和连续性约束。</p>
          </div>
          <ClipboardList className="title-icon" size={28} />
        </div>

        <form className="form-stack" onSubmit={handleSubmit}>
          <label>
            <span>世界观设定</span>
            <textarea
              value={form.world_setting}
              onChange={(event: ChangeEvent<HTMLTextAreaElement>) => updateField("world_setting", event.target.value)}
              rows={5}
              placeholder="人类文明在星门网络崩塌后三百年分裂为多个城邦舰队。"
            />
          </label>
          <label>
            <span>主线冲突</span>
            <textarea
              value={form.main_conflict}
              onChange={(event: ChangeEvent<HTMLTextAreaElement>) => updateField("main_conflict", event.target.value)}
              rows={4}
              placeholder="主角必须查清旧帝国覆灭真相，同时阻止新星门战争。"
            />
          </label>
          <div className="form-grid">
            <label>
              <span>主题，每行一条</span>
              <textarea
                value={form.themes}
                onChange={(event: ChangeEvent<HTMLTextAreaElement>) => updateField("themes", event.target.value)}
                rows={4}
                placeholder={"身份\n责任\n文明记忆"}
              />
            </label>
            <label>
              <span>叙事视角</span>
              <select
                value={form.narrative_pov}
                onChange={(event: ChangeEvent<HTMLSelectElement>) => updateField("narrative_pov", event.target.value as StoryBibleForm["narrative_pov"])}
              >
                <option value="first_person">first_person</option>
                <option value="third_person_limited">third_person_limited</option>
                <option value="third_person_omniscient">third_person_omniscient</option>
              </select>
            </label>
          </div>
          <label>
            <span>风格约束</span>
            <textarea
              value={form.style_guide}
              onChange={(event: ChangeEvent<HTMLTextAreaElement>) => updateField("style_guide", event.target.value)}
              rows={3}
            />
          </label>
          <div className="form-grid">
            <label>
              <span>禁用元素，每行一条</span>
              <textarea
                value={form.forbidden_elements}
                onChange={(event: ChangeEvent<HTMLTextAreaElement>) => updateField("forbidden_elements", event.target.value)}
                rows={5}
                placeholder={"机械降神式反转\n无铺垫复活"}
              />
            </label>
            <label>
              <span>连续性规则，每行一条</span>
              <textarea
                value={form.continuity_rules}
                onChange={(event: ChangeEvent<HTMLTextAreaElement>) => updateField("continuity_rules", event.target.value)}
                rows={5}
                placeholder="角色已知信息不得超过其亲历或被告知的信息。"
              />
            </label>
          </div>

          {mutation.error ? (
            <div className="error-block" role="alert">
              <AlertCircle size={18} />
              <div>
                <strong>更新失败</strong>
                <span>{apiErrorText(mutation.error)}</span>
              </div>
            </div>
          ) : null}

          {mutation.isPending ? (
            <div className="loading-block">
              <Loader2 size={18} />
              <span>正在保存故事圣经...</span>
            </div>
          ) : null}

          <button className="primary-button" type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? <Loader2 size={18} /> : <Check size={18} />}
            <span>{mutation.isPending ? "保存中" : "保存故事圣经"}</span>
          </button>
        </form>
      </section>

      <aside className="panel side-panel">
        <p className="eyebrow">当前版本</p>
        {mutation.isPending ? (
          <div className="skeleton-stack" aria-label="加载中">
            <span />
            <span />
            <span />
          </div>
        ) : (
          <dl className="detail-grid">
            <div>
              <dt>故事圣经 ID</dt>
              <dd>{snapshot.story_bible.id}</dd>
            </div>
            <div>
              <dt>版本</dt>
              <dd>v{snapshot.story_bible.version}</dd>
            </div>
            <div>
              <dt>主题</dt>
              <dd>{snapshot.story_bible.themes.length ? snapshot.story_bible.themes.join("、") : "暂无主题"}</dd>
            </div>
            <div>
              <dt>更新时间</dt>
              <dd>{snapshot.story_bible.updated_at}</dd>
            </div>
          </dl>
        )}
        {mutation.data ? (
          <div className="success-block stacked-success">
            <Check size={18} />
            <div>
              <strong>保存成功</strong>
              <span>故事圣经已更新到 v{mutation.data.story_bible.version}</span>
            </div>
          </div>
        ) : null}
      </aside>
    </div>
  );
}
