import { ClipboardList, FilePlus2, ListChecks, Loader2, TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { navigateTo } from "../App";
import { readProjectSnapshotFor } from "../stores/editorStore";
import type { ProjectSnapshot } from "../types/api";

interface ProjectWorkspacePageProps {
  projectId: string;
}

export function ProjectWorkspacePage({ projectId }: ProjectWorkspacePageProps) {
  const [isLoading, setIsLoading] = useState(true);
  const [snapshot, setSnapshot] = useState<ProjectSnapshot | null>(null);
  const [hasMismatch, setHasMismatch] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const current = readProjectSnapshotFor(projectId);
      setSnapshot(current);
      setHasMismatch(current === null);
      setIsLoading(false);
    }, 120);
    return () => window.clearTimeout(timer);
  }, [projectId]);

  if (isLoading) {
    return (
      <section className="panel">
        <p className="eyebrow">/projects/:projectId/workspace</p>
        <h1>项目工作台</h1>
        <div className="loading-block">
          <Loader2 size={18} />
          <span>正在读取最近项目...</span>
        </div>
      </section>
    );
  }

  if (!snapshot) {
    return (
      <section className="panel">
        <p className="eyebrow">/projects/:projectId/workspace</p>
        <h1>项目工作台</h1>
        {hasMismatch ? (
          <div className="error-block" role="alert">
            <TriangleAlert size={18} />
            <div>
              <strong>无法载入当前项目</strong>
              <span>本地最近项目缓存与 URL 不一致，请先重新创建项目。</span>
            </div>
          </div>
        ) : null}
        <div className="empty-block">
          <strong>请先创建项目</strong>
          <span>后端 MVP 暂未提供项目列表或项目详情接口，工作台只展示最近一次成功创建的项目。</span>
        </div>
        <button className="primary-button narrow-button" type="button" onClick={() => navigateTo("/projects/new")}>
          <FilePlus2 size={18} />
          <span>新建项目</span>
        </button>
      </section>
    );
  }

  const { project, story_bible: storyBible } = snapshot;

  return (
    <div className="workspace-layout">
      <section className="panel">
        <p className="eyebrow">/projects/:projectId/workspace</p>
        <div className="title-row">
          <div>
            <h1>{project.title}</h1>
            <p className="lede">{project.premise}</p>
          </div>
          <span className="status-pill">{project.status}</span>
        </div>

        <dl className="meta-grid">
          <div>
            <dt>项目 ID</dt>
            <dd>{project.id}</dd>
          </div>
          <div>
            <dt>题材</dt>
            <dd>{project.genre}</dd>
          </div>
          <div>
            <dt>目标读者</dt>
            <dd>{project.target_reader}</dd>
          </div>
          <div>
            <dt>计划规模</dt>
            <dd>
              {project.planned_chapter_count} 章 · 单章约 {project.chapter_word_target} 字
            </dd>
          </div>
          <div>
            <dt>语言</dt>
            <dd>{project.language}</dd>
          </div>
          <div>
            <dt>更新时间</dt>
            <dd>{project.updated_at}</dd>
          </div>
        </dl>
      </section>

      <aside className="panel">
        <p className="eyebrow">下一步</p>
        <div className="action-grid">
          <button className="action-button" type="button" onClick={() => navigateTo(`/projects/${project.id}/story-bible`)}>
            <ClipboardList size={20} />
            <span>
              <strong>编辑故事圣经</strong>
              <small>当前版本 v{storyBible.version}</small>
            </span>
          </button>
          <button className="action-button" type="button" onClick={() => navigateTo(`/projects/${project.id}/chapters/plan`)}>
            <ListChecks size={20} />
            <span>
              <strong>创建章节规划</strong>
              <small>生成任务会进入 job 状态页</small>
            </span>
          </button>
          <button className="action-button muted-action" type="button" onClick={() => navigateTo("/projects/new")}>
            <FilePlus2 size={20} />
            <span>
              <strong>新建项目</strong>
              <small>覆盖本地最近项目缓存</small>
            </span>
          </button>
        </div>
      </aside>
    </div>
  );
}
