import { create } from "zustand";
import type { Project } from "../types/api";

interface StudioStore {
  currentProjectId: string | null;
  recentProjects: Project[];
  darkMode: boolean;
  focusMode: boolean;
  setCurrentProjectId: (projectId: string | null) => void;
  setRecentProjects: (projects: Project[]) => void;
  toggleDarkMode: () => void;
  toggleFocusMode: () => void;
}

export const useStudioStore = create<StudioStore>((set) => ({
  currentProjectId: window.localStorage.getItem("novel-agent-current-project"),
  recentProjects: [],
  darkMode: window.localStorage.getItem("novel-agent-theme") === "dark",
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
  toggleDarkMode: () =>
    set((state) => {
      const next = !state.darkMode;
      window.localStorage.setItem("novel-agent-theme", next ? "dark" : "light");
      return { darkMode: next };
    }),
  toggleFocusMode: () => set((state) => ({ focusMode: !state.focusMode })),
}));
