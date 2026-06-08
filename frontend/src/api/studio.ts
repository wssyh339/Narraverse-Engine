import { API_BASE_URL, api, unwrap } from "./client";
import type {
  AgentRun,
  Chapter,
  Character,
  EditorProposal,
  ForeshadowingItem,
  GenerationJob,
  GraphEdge,
  GraphNode,
  Project,
  Note,
  StoryBible,
  StoryEntity,
  VersionSnapshot,
  Volume,
  WorkflowDefinition,
  WorldFact,
  CreationStarBasicInfo,
  CreationStarCard,
  CreationStarOptions,
  CanonRunPayload,
  CanonRunResult,
} from "../types/api";

export interface CreateProjectPayload {
  title: string;
  genre: string;
  target_reader: string;
  premise: string;
  style_guide: string;
  language: string;
  planned_chapter_count: number;
  chapter_word_target: number;
  target_words?: number;
  initial_idea?: string;
}

export type ImportanceLevel = "core" | "major" | "medium" | "minor";
export type RoleType = "protagonist" | "antagonist" | "supporting" | "minor";
export type SettingTarget = "characters" | "entities" | "world_facts" | "all";

export interface CharacterPayload {
  name: string;
  aliases?: string[];
  role_type?: RoleType;
  importance_level?: ImportanceLevel;
  importance_score?: number;
  summary?: string;
  appearance?: string;
  personality?: string;
  goals?: string[];
  motivations?: string[];
  secrets?: string[];
  abilities?: string[];
  weaknesses?: string[];
  character_arc?: string;
  current_status?: string;
  related_entity_ids?: string[];
  related_character_ids?: string[];
  updated_reason?: string;
}

export interface EntityPayload {
  entity_type?: "location" | "organization" | "item" | "event" | "concept" | "rule" | "clue" | "timeline_event";
  name: string;
  importance_level?: ImportanceLevel;
  importance_score?: number;
  description?: string;
  current_status?: string;
  source?: string;
}

export interface WorldFactPayload {
  category?: "geography" | "history" | "magic_rule" | "technology" | "politics" | "culture" | "economy" | "religion" | "organization" | "timeline" | "taboo";
  title: string;
  content?: string;
  importance_level?: ImportanceLevel;
  importance_score?: number;
  confidence?: number;
  related_entity_ids?: string[];
}

export interface GenerateSettingPayload {
  target: SettingTarget;
  instruction?: string;
  count?: number;
  model?: string;
}

export type CreationStarStep = "worldview" | "protagonist" | "project_bible" | "world_rules" | "title";

export interface CreationStarDrawPayload {
  step: CreationStarStep;
  basic_info?: CreationStarBasicInfo;
  selected_worldview?: Record<string, unknown>;
  selected_protagonist?: Record<string, unknown>;
  project_bible?: Record<string, unknown>;
  world_rules?: Record<string, unknown>;
  manual_input?: string;
  count?: number;
  model?: string;
}

export interface CreationStarCommitPayload {
  basic_info: CreationStarBasicInfo;
  selected_worldview: Record<string, unknown>;
  selected_protagonist: Record<string, unknown>;
  selected_title?: Record<string, unknown>;
  project_bible: Record<string, unknown>;
  world_rules: Record<string, unknown>;
  user_note?: string;
  model?: string;
}

export interface ForeshadowingPayload {
  chapter_id?: string | null;
  content: string;
  planted_chapter_id?: string | null;
  planned_payoff_chapter_id?: string | null;
  actual_payoff_chapter_id?: string | null;
  planned_payoff?: string;
  payoff_status?: "planned" | "planted" | "paid_off" | "abandoned" | "candidate";
  importance_level?: ImportanceLevel;
  importance_score?: number;
  related_character_ids?: string[];
  related_entity_ids?: string[];
  source?: "manual" | "agent";
}

export interface ForeshadowingSuggestion {
  content: string;
  planned_payoff: string;
  payoff_status: "candidate";
  importance_level: ImportanceLevel;
  importance_score: number;
  related_character_ids: string[];
  related_entity_ids: string[];
  source: "agent";
}

export type ChapterChatMode = "revise" | "polish" | "expand" | "tighten" | "continue";

export interface ChapterChatPayload {
  mode: ChapterChatMode;
  instruction: string;
  selected_text?: string;
  chapter_text?: string;
  selection_start?: number | null;
  selection_end?: number | null;
  model?: string;
}

export interface ChapterChatSelection {
  start: number | null;
  end: number | null;
  has_selection: boolean;
}

export type ChapterChatStreamEvent =
  | {
      type: "meta";
      provider: string;
      model: string;
      selection: ChapterChatSelection;
      message: string;
    }
  | { type: "delta"; text: string }
  | {
      type: "result";
      replacement: string;
      reasoning: string;
      checklist: string[];
      selection: ChapterChatSelection;
      provider: string;
      model: string;
      used_remote_model: boolean;
    }
  | { type: "done" };

function emitSseBlock(block: string, onEvent: (event: ChapterChatStreamEvent) => void) {
  const data = block
    .split(/\r?\n/)
    .filter((line) => line.startsWith("data: "))
    .map((line) => line.slice(6))
    .join("\n");
  if (!data) return;
  onEvent(JSON.parse(data) as ChapterChatStreamEvent);
}

export async function streamChapterChat(
  projectId: string,
  chapterId: string,
  payload: ChapterChatPayload,
  onEvent: (event: ChapterChatStreamEvent) => void,
  signal?: AbortSignal,
) {
  const response = await fetch(`${API_BASE_URL}/projects/${projectId}/chapters/${chapterId}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || "章节 AI 对话请求失败");
  }
  if (!response.body) {
    throw new Error("当前浏览器不支持流式响应读取");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split(/\n\n/);
    buffer = blocks.pop() ?? "";
    blocks.forEach((block) => emitSseBlock(block, onEvent));
  }
  buffer += decoder.decode();
  if (buffer.trim()) emitSseBlock(buffer, onEvent);
}

export const studioApi = {
  listProjects: () => unwrap<{ projects: Project[]; stats: Record<string, number> }>(api.get("/projects")),
  createProject: (payload: CreateProjectPayload) => unwrap<{ project: Project; story_bible: StoryBible }>(api.post("/projects", payload)),
  updateProject: (projectId: string, payload: Partial<Project>) => unwrap<{ project: Project }>(api.put(`/projects/${projectId}`, payload)),
  deleteProject: (projectId: string) => unwrap<{ project: Project; project_id: string; deleted: boolean }>(api.delete(`/projects/${projectId}`)),
  getProject: (projectId: string) => unwrap<{ project: Project; story_bible: StoryBible; chapter_count: number; completed_chapter_count: number }>(api.get(`/projects/${projectId}`)),
  getState: (projectId: string) => unwrap<{ state: ProjectState }>(api.get(`/projects/${projectId}/state`)),
  generateStoryBible: (projectId: string, initial_idea = "") =>
    unwrap<{ job: GenerationJob; story_bible: StoryBible; canon_updates: Record<string, unknown> }>(
      api.post(`/projects/${projectId}/story-bible/generate`, { initial_idea }),
    ),
  updateStoryBible: (projectId: string, payload: Partial<StoryBible>) =>
    unwrap<{ story_bible: StoryBible }>(api.put(`/projects/${projectId}/story-bible`, payload)),
  planChapters: (projectId: string, payload: Record<string, unknown>) =>
    unwrap<{ job: GenerationJob; chapters: Chapter[]; outline_plan: Record<string, unknown> }>(
      api.post(`/projects/${projectId}/chapters/plan`, payload),
    ),
  listChapters: (projectId: string) => unwrap<{ chapters: Chapter[] }>(api.get(`/projects/${projectId}/chapters`)),
  getChapter: (projectId: string, chapterId: string) => unwrap<{ chapter: Chapter }>(api.get(`/projects/${projectId}/chapters/${chapterId}`)),
  updateChapter: (projectId: string, chapterId: string, payload: Partial<Chapter>) =>
    unwrap<{ chapter: Chapter }>(api.put(`/projects/${projectId}/chapters/${chapterId}`, payload)),
  createChapter: (projectId: string, payload: { volume_no: number; title: string; outline?: string; word_target?: number }) =>
    unwrap<{ chapter: Chapter }>(api.post(`/projects/${projectId}/chapters`, payload)),
  reorderChapters: (projectId: string, chapter_ids: string[]) =>
    unwrap<{ chapters: Chapter[] }>(api.post(`/projects/${projectId}/chapters/reorder`, { chapter_ids })),
  listTrash: (projectId: string) => unwrap<{ chapters: Chapter[] }>(api.get(`/projects/${projectId}/chapters/trash`)),
  trashChapter: (projectId: string, chapterId: string) =>
    unwrap<{ chapter: Chapter }>(api.post(`/projects/${projectId}/chapters/${chapterId}/trash`)),
  trashChapters: (projectId: string, chapter_ids: string[]) =>
    unwrap<{ deleted: boolean; chapter_ids: string[]; chapters: Chapter[] }>(
      api.post(`/projects/${projectId}/chapters/trash/batch`, { chapter_ids }),
    ),
  restoreChapter: (projectId: string, chapterId: string) =>
    unwrap<{ chapter: Chapter }>(api.post(`/projects/${projectId}/chapters/${chapterId}/restore`)),
  snapshotChapter: (projectId: string, chapterId: string, user_note = "") =>
    unwrap<{ version: VersionSnapshot }>(api.post(`/projects/${projectId}/chapters/${chapterId}/snapshot`, { user_note })),
  listVolumes: (projectId: string) => unwrap<{ volumes: Volume[] }>(api.get(`/projects/${projectId}/volumes`)),
  createVolume: (projectId: string, payload: { title: string; outline?: string; volume_no?: number }) =>
    unwrap<{ volume: Volume }>(api.post(`/projects/${projectId}/volumes`, payload)),
  updateVolume: (projectId: string, volumeId: string, payload: Partial<Volume>) =>
    unwrap<{ volume: Volume }>(api.put(`/projects/${projectId}/volumes/${volumeId}`, payload)),
  deleteVolume: (projectId: string, volumeId: string) =>
    unwrap<{ deleted: boolean; volume_id: string }>(api.delete(`/projects/${projectId}/volumes/${volumeId}`)),
  listNotes: (projectId: string) => unwrap<{ notes: Note[] }>(api.get(`/projects/${projectId}/notes`)),
  createNote: (projectId: string, payload: { title: string; content?: string; note_type?: Note["note_type"]; parent_id?: string | null; is_pinned?: boolean }) =>
    unwrap<{ note: Note }>(api.post(`/projects/${projectId}/notes`, payload)),
  updateNote: (projectId: string, noteId: string, payload: Partial<Note>) =>
    unwrap<{ note: Note }>(api.put(`/projects/${projectId}/notes/${noteId}`, payload)),
  deleteNote: (projectId: string, noteId: string) =>
    unwrap<{ deleted: boolean; note_id: string }>(api.delete(`/projects/${projectId}/notes/${noteId}`)),
  listProposals: (projectId: string, chapterId?: string) =>
    unwrap<{ proposals: EditorProposal[] }>(api.get(`/projects/${projectId}/proposals`, { params: { chapter_id: chapterId } })),
  createProposal: (projectId: string, chapterId: string, payload: { tool_name: string; instruction?: string; selected_text?: string }) =>
    unwrap<{ proposal: EditorProposal }>(api.post(`/projects/${projectId}/chapters/${chapterId}/proposals`, payload)),
  applyProposal: (projectId: string, proposalId: string) =>
    unwrap<{ proposal: EditorProposal; chapter: Chapter }>(api.post(`/projects/${projectId}/proposals/${proposalId}/apply`)),
  rejectProposal: (projectId: string, proposalId: string) =>
    unwrap<{ proposal: EditorProposal }>(api.post(`/projects/${projectId}/proposals/${proposalId}/reject`)),
  backupProject: (projectId: string) => unwrap<{ backup: Record<string, unknown> }>(api.get(`/projects/${projectId}/backup`)),
  draftChapter: (projectId: string, chapterId: string, user_instruction = "") =>
    unwrap<{ job: GenerationJob; chapter: Chapter }>(api.post(`/projects/${projectId}/chapters/${chapterId}/draft`, { user_instruction })),
  listAgents: () => unwrap<{ agents: AgentConfig[] }>(api.get("/agents")),
  getCreationStarOptions: () => unwrap<{ options: CreationStarOptions }>(api.get("/creation-star/options")),
  drawCreationStar: (projectId: string, payload: CreationStarDrawPayload) =>
    unwrap<{
      job: GenerationJob;
      step: CreationStarStep;
      draw_id?: string;
      prompt_snapshot?: Record<string, unknown>;
      cards?: CreationStarCard[];
      project_bible?: Record<string, unknown>;
      world_rules?: Record<string, unknown>;
    }>(api.post(`/projects/${projectId}/creation-star/draw`, payload)),
  commitCreationStar: (projectId: string, payload: CreationStarCommitPayload) =>
    unwrap<{
      job: GenerationJob;
      project: Project;
      story_bible: StoryBible;
      character: Character;
      entities: StoryEntity[];
      world_facts: WorldFact[];
      version: VersionSnapshot;
    }>(api.post(`/projects/${projectId}/creation-star/commit`, payload)),
  runCanonStudio: (projectId: string, payload: CanonRunPayload) =>
    unwrap<CanonRunResult>(api.post(`/projects/${projectId}/canon-studio/run`, payload)),
  getCanonStore: (projectId: string) =>
    unwrap<{ store: Record<string, unknown> }>(api.get(`/projects/${projectId}/canon-studio/store`)),
  getCanonFinalOutline: (projectId: string) =>
    unwrap<{ path: string; markdown: string }>(api.get(`/projects/${projectId}/canon-studio/final-outline`)),
  listWorkflows: () => unwrap<{ workflows: WorkflowDefinition[] }>(api.get("/workflows")),
  updateAgentPrompt: (agentName: string, prompt: string) => unwrap<{ agent: AgentConfig }>(api.put(`/agents/${agentName}/prompt`, { prompt })),
  getJob: (jobId: string) => unwrap<{ job: GenerationJob }>(api.get(`/jobs/${jobId}`)),
  getAgentRuns: (jobId: string) => unwrap<{ agent_runs: AgentRun[] }>(api.get(`/jobs/${jobId}/agent-runs`)),
  listCharacters: (projectId: string) => unwrap<{ characters: Character[] }>(api.get(`/projects/${projectId}/characters`)),
  createCharacter: (projectId: string, payload: CharacterPayload) =>
    unwrap<{ character: Character }>(api.post(`/projects/${projectId}/characters`, payload)),
  updateCharacter: (projectId: string, characterId: string, payload: Partial<CharacterPayload>) =>
    unwrap<{ character: Character }>(api.put(`/projects/${projectId}/characters/${characterId}`, payload)),
  deleteCharacter: (projectId: string, characterId: string) =>
    unwrap<{ deleted: boolean; character_id: string }>(api.delete(`/projects/${projectId}/characters/${characterId}`)),
  listEntities: (projectId: string) => unwrap<{ entities: StoryEntity[] }>(api.get(`/projects/${projectId}/entities`)),
  createEntity: (projectId: string, payload: EntityPayload) =>
    unwrap<{ entity: StoryEntity }>(api.post(`/projects/${projectId}/entities`, payload)),
  updateEntity: (projectId: string, entityId: string, payload: Partial<EntityPayload>) =>
    unwrap<{ entity: StoryEntity }>(api.put(`/projects/${projectId}/entities/${entityId}`, payload)),
  deleteEntity: (projectId: string, entityId: string) =>
    unwrap<{ deleted: boolean; entity_id: string }>(api.delete(`/projects/${projectId}/entities/${entityId}`)),
  listWorldFacts: (projectId: string) => unwrap<{ world_facts: WorldFact[] }>(api.get(`/projects/${projectId}/world-facts`)),
  createWorldFact: (projectId: string, payload: WorldFactPayload) =>
    unwrap<{ world_fact: WorldFact }>(api.post(`/projects/${projectId}/world-facts`, payload)),
  updateWorldFact: (projectId: string, factId: string, payload: Partial<WorldFactPayload>) =>
    unwrap<{ world_fact: WorldFact }>(api.put(`/projects/${projectId}/world-facts/${factId}`, payload)),
  deleteWorldFact: (projectId: string, factId: string) =>
    unwrap<{ deleted: boolean; world_fact_id: string }>(api.delete(`/projects/${projectId}/world-facts/${factId}`)),
  generateSettings: (projectId: string, payload: GenerateSettingPayload) =>
    unwrap<{ job: GenerationJob; characters: Character[]; entities: StoryEntity[]; world_facts: WorldFact[] }>(
      api.post(`/projects/${projectId}/settings/generate`, payload),
    ),
  listForeshadowing: (projectId: string) =>
    unwrap<{ foreshadowing_items: ForeshadowingItem[] }>(api.get(`/projects/${projectId}/foreshadowing`)),
  createForeshadowing: (projectId: string, payload: ForeshadowingPayload) =>
    unwrap<{ foreshadowing_item: ForeshadowingItem }>(api.post(`/projects/${projectId}/foreshadowing`, payload)),
  updateForeshadowing: (projectId: string, itemId: string, payload: Partial<ForeshadowingPayload>) =>
    unwrap<{ foreshadowing_item: ForeshadowingItem }>(api.put(`/projects/${projectId}/foreshadowing/${itemId}`, payload)),
  deleteForeshadowing: (projectId: string, itemId: string) =>
    unwrap<{ deleted: boolean; foreshadowing_id: string }>(api.delete(`/projects/${projectId}/foreshadowing/${itemId}`)),
  payoffForeshadowing: (projectId: string, itemId: string, actual_payoff_chapter_id: string, payoff_note = "") =>
    unwrap<{ foreshadowing_item: ForeshadowingItem }>(
      api.post(`/projects/${projectId}/foreshadowing/${itemId}/payoff`, { actual_payoff_chapter_id, payoff_note }),
    ),
  suggestForeshadowing: (project_id: string, chapter_id?: string, instruction = "") =>
    unwrap<{ suggestions: ForeshadowingSuggestion[]; canon_context_used: Record<string, unknown> }>(
      api.post("/tools/foreshadowing", { project_id, chapter_id, instruction }),
    ),
  getGraph: (projectId: string) => unwrap<{ graph: { nodes: GraphNode[]; edges: GraphEdge[] } }>(api.get(`/projects/${projectId}/graph`)),
  canonContext: (projectId: string, chapterId?: string) =>
    unwrap<{ canon_context: Record<string, unknown> }>(api.get(`/projects/${projectId}/canon/context`, { params: { chapter_id: chapterId } })),
  refreshCanon: (projectId: string) => unwrap<{ canon_updates: Record<string, unknown> }>(api.post(`/projects/${projectId}/canon/refresh`)),
  listVersions: (chapterId?: string) => unwrap<{ versions: VersionSnapshot[] }>(api.get(chapterId ? `/versions/${chapterId}` : "/versions")),
  compareVersions: (left_version_id: string, right_version_id: string) =>
    unwrap<{ diff: string[]; left: VersionSnapshot; right: VersionSnapshot }>(api.post("/versions/compare", { left_version_id, right_version_id })),
  rollbackVersion: (versionId: string, user_note = "") =>
    unwrap<{ version: VersionSnapshot; rolled_back: boolean }>(api.post(`/versions/${versionId}/rollback`, { user_note })),
  batchGenerate: (project_id: string, chapter_start: number, chapter_end: number) =>
    unwrap<{ job: GenerationJob; chapters: Chapter[] }>(api.post("/write/batch-generate", { project_id, chapter_start, chapter_end })),
  pauseJob: (job_id: string, reason = "") =>
    unwrap<{ job: GenerationJob }>(api.post("/write/pause", { job_id, reason })),
  resumeJob: (job_id: string, reason = "") =>
    unwrap<{ job: GenerationJob }>(api.post("/write/resume", { job_id, reason })),
  cancelJob: (job_id: string, reason = "") =>
    unwrap<{ job: GenerationJob }>(api.post("/write/cancel", { job_id, reason })),
  exportProject: (project_id: string, format: string) =>
    unwrap<{ export_job: { output_path: string; status: string }; preview: string }>(api.post("/export", { project_id, format })),
  summary: (project_id: string) => unwrap<{ summary: string; chapter_count: number }>(api.post("/tools/summary", { project_id })),
  learnStyle: (project_id: string, name: string, sample_text: string) =>
    unwrap<{ style_profile: { id: string; name: string; profile: string } }>(api.post("/tools/learn-style", { project_id, name, sample_text })),
  queryKnowledge: (project_id: string, question: string) =>
    unwrap<{ answer: string; matches: unknown[] }>(api.post("/tools/query-knowledge", { project_id, question })),
};

export interface AgentConfig {
  name: string;
  role: string;
  order: number;
  prompt: string;
}

export interface ProjectState {
  project: Project;
  story_bible: StoryBible | null;
  characters: Character[];
  chapters: Chapter[];
  story_entities: StoryEntity[];
  world_facts: WorldFact[];
  graph: { nodes: GraphNode[]; edges: GraphEdge[] };
  continuity_issues: Array<Record<string, unknown>>;
  foreshadowing_items: ForeshadowingItem[];
}
