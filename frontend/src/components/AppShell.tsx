import { BookOpen, ClipboardList, FilePlus2, Library, ListChecks, PanelRight, Wand2 } from "lucide-react";
import type { ReactNode } from "react";
import { navigateTo } from "../App";
import { readProjectSnapshot } from "../stores/editorStore";

interface AppShellProps {
  children: ReactNode;
  currentPath: string;
}

export function AppShell({ children, currentPath }: AppShellProps) {
  const snapshot = readProjectSnapshot();
  const project = snapshot?.project ?? null;
  const workspacePath = project ? `/projects/${project.id}/workspace` : "/projects/new";
  const storyBiblePath = project ? `/projects/${project.id}/story-bible` : "/projects/new";
  const chapterPlanPath = project ? `/projects/${project.id}/chapters/plan` : "/projects/new";

  return (
    <div className="app-frame">
      <aside className="sidebar" aria-label="主导航">
        <div className="brand-lockup">
          <div className="brand-mark" aria-hidden="true">
            <BookOpen size={20} />
          </div>
          <div>
            <strong>长篇写作 Agent</strong>
            <span>本地优先工作台</span>
          </div>
        </div>

        <nav className="nav-stack">
          <button
            className={currentPath === workspacePath && project ? "nav-item active" : "nav-item"}
            type="button"
            onClick={() => navigateTo(workspacePath)}
          >
            <Library size={18} />
            <span>工作台</span>
          </button>
          <button
            className={currentPath === "/projects/new" ? "nav-item active" : "nav-item"}
            type="button"
            onClick={() => navigateTo("/projects/new")}
          >
            <FilePlus2 size={18} />
            <span>新建项目</span>
          </button>
          <button
            className={currentPath === storyBiblePath && project ? "nav-item active" : "nav-item"}
            type="button"
            onClick={() => navigateTo(storyBiblePath)}
          >
            <ClipboardList size={18} />
            <span>故事圣经</span>
          </button>
          <button
            className={currentPath === chapterPlanPath && project ? "nav-item active" : "nav-item"}
            type="button"
            onClick={() => navigateTo(chapterPlanPath)}
          >
            <ListChecks size={18} />
            <span>章节规划</span>
          </button>
        </nav>

        <div className="sidebar-card">
          <div className="sidebar-card-title">
            <PanelRight size={16} />
            <span>当前项目</span>
          </div>
          {project ? (
            <div className="current-project">
              <strong>{project.title}</strong>
              <span>{project.genre}</span>
              <code>{project.id}</code>
            </div>
          ) : (
            <p>请先创建项目，工作台会显示最近一次成功创建的项目。</p>
          )}
        </div>

        <div className="sidebar-note">
          <Wand2 size={16} />
          <span>AI 调用只由后端发起</span>
        </div>
      </aside>
      <main className="main-surface">{children}</main>
    </div>
  );
}
