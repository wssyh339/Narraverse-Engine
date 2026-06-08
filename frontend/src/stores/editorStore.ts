import type { ProjectSnapshot, StoryBible } from "../types/api";

const currentProjectKey = "novel-agent:current-project";

export function saveProjectSnapshot(snapshot: ProjectSnapshot): void {
  localStorage.setItem(currentProjectKey, JSON.stringify(snapshot));
}

export function readProjectSnapshot(): ProjectSnapshot | null {
  const raw = localStorage.getItem(currentProjectKey);
  if (!raw) {
    return null;
  }

  try {
    return JSON.parse(raw) as ProjectSnapshot;
  } catch {
    localStorage.removeItem(currentProjectKey);
    return null;
  }
}

export function readProjectSnapshotFor(projectId: string): ProjectSnapshot | null {
  const snapshot = readProjectSnapshot();
  if (!snapshot || snapshot.project.id !== projectId) {
    return null;
  }
  return snapshot;
}

export function updateStoredStoryBible(storyBible: StoryBible): ProjectSnapshot | null {
  const snapshot = readProjectSnapshotFor(storyBible.project_id);
  if (!snapshot) {
    return null;
  }
  const nextSnapshot = { ...snapshot, story_bible: storyBible };
  saveProjectSnapshot(nextSnapshot);
  return nextSnapshot;
}
