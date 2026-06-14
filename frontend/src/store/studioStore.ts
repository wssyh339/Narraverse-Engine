import { create } from "zustand";
import type { Project } from "../types/api";

export type AppearanceMode = "light" | "dark" | "eye-care";

const appearanceModes: AppearanceMode[] = ["light", "dark", "eye-care"];

function getInitialAppearanceMode(): AppearanceMode {
  const savedMode = window.localStorage.getItem("novel-agent-appearance");
  if (savedMode === "light" || savedMode === "dark" || savedMode === "eye-care") {
    return savedMode;
  }
  if (window.localStorage.getItem("novel-agent-eye-care") === "true") {
    return "eye-care";
  }
  return window.localStorage.getItem("novel-agent-theme") === "dark" ? "dark" : "light";
}

function persistAppearanceMode(mode: AppearanceMode) {
  window.localStorage.setItem("novel-agent-appearance", mode);
  window.localStorage.setItem("novel-agent-theme", mode === "dark" ? "dark" : "light");
  window.localStorage.setItem("novel-agent-eye-care", String(mode === "eye-care"));
}

interface StudioStore {
  currentProjectId: string | null;
  recentProjects: Project[];
  appearanceMode: AppearanceMode;
  focusMode: boolean;
  setCurrentProjectId: (projectId: string | null) => void;
  setRecentProjects: (projects: Project[]) => void;
  cycleAppearanceMode: () => void;
  toggleFocusMode: () => void;
}

export const useStudioStore = create<StudioStore>((set) => ({
  currentProjectId: window.localStorage.getItem("novel-agent-current-project"),
  recentProjects: [],
  appearanceMode: getInitialAppearanceMode(),
  focusMode: false,
  setCurrentProjectId: (projectId) => {
    if (projectId) {
      window.localStorage.setItem("novel-agent-current-project", projectId);
    } else {
      window.localStorage.removeItem("novel-agent-current-project");
    }
    set({ currentProjectId: projectId });
  },
  setRecentProjects: (projects) => set({ recentProjects: projects }),
  cycleAppearanceMode: () =>
    set((state) => {
      const currentIndex = appearanceModes.indexOf(state.appearanceMode);
      const next = appearanceModes[(currentIndex + 1) % appearanceModes.length];
      persistAppearanceMode(next);
      return { appearanceMode: next };
    }),
  toggleFocusMode: () => set((state) => ({ focusMode: !state.focusMode })),
}));
