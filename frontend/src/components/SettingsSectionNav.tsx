import { BookOpen, FileText, GitBranch, Network, Sparkles, Users } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";

type SettingsSection = "profile" | "characters" | "world" | "graph" | "foreshadowing";

interface SettingsSectionNavProps {
  active: SettingsSection;
}

const sections: Array<{
  key: SettingsSection;
  title: string;
  description: string;
  icon: typeof Users;
}> = [
  { key: "profile", title: "作品资料", description: "书名、卖点、读者画像和故事圣经", icon: FileText },
  { key: "characters", title: "角色卡", description: "人物目标、关系、弧光和重要度", icon: Users },
  { key: "world", title: "世界与实体", description: "规则、地点、组织、物件和线索", icon: BookOpen },
  { key: "graph", title: "关系图谱", description: "角色、实体和世界事实的关系网络", icon: Network },
  { key: "foreshadowing", title: "伏笔", description: "预埋、计划回收和实际回收", icon: GitBranch },
];

export function SettingsSectionNav({ active }: SettingsSectionNavProps) {
  const { projectId = "" } = useParams();
  const navigate = useNavigate();

  return (
    <section className="settings-section-nav">
      <div className="settings-section-heading">
        <div>
          <p>Canon Settings</p>
          <h2>设定工作台</h2>
          <span>作品信息、正典设定、图谱和伏笔统一维护；正文生成前会读取这里的正式上下文。</span>
        </div>
        <div className="settings-section-mark">
          <Sparkles size={18} />
        </div>
      </div>
      <div className="settings-section-grid">
        {sections.map((section) => {
          const Icon = section.icon;
          const isActive = section.key === active;
          return (
            <button
              key={section.key}
              type="button"
              className={`settings-section-tile ${isActive ? "is-active" : ""}`}
              onClick={() => navigate(`/projects/${projectId}/settings/${section.key}`)}
            >
              <span className="settings-section-icon"><Icon size={18} /></span>
              <span className="settings-section-copy">
                <strong>{section.title}</strong>
                <small>{section.description}</small>
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
