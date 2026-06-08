import { ArrowLeft, FilePlus2 } from "lucide-react";
import { navigateTo } from "../App";

interface ProjectNavProps {
  projectId?: string;
  title: string;
}

export function ProjectNav({ projectId, title }: ProjectNavProps) {
  return (
    <div className="page-toolbar">
      <button className="icon-button" type="button" onClick={() => navigateTo(projectId ? `/projects/${projectId}/workspace` : "/projects/new")} title="返回工作台">
        <ArrowLeft size={18} />
      </button>
      <strong>{title}</strong>
      <button className="text-button subtle" type="button" onClick={() => navigateTo("/projects/new")}>
        <FilePlus2 size={16} />
        <span>新建项目</span>
      </button>
    </div>
  );
}
