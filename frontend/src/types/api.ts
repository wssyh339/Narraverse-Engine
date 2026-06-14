export type ApiErrorCode =
  | "VALIDATION_ERROR"
  | "NOT_FOUND"
  | "CONFLICT"
  | "LLM_PROVIDER_ERROR"
  | "JOB_FAILED"
  | "INTERNAL_ERROR";

export interface ApiErrorPayload {
  code: ApiErrorCode;
  message: string;
  details: unknown;
}

export interface ApiResponse<TData> {
  success: boolean;
  data: TData | null;
  error: ApiErrorPayload | null;
  request_id: string;
  timestamp: string;
}

export interface Project {
  id: string;
  title: string;
  genre: string;
  target_reader: string;
  premise: string;
  style_guide: string;
  language: string;
  planned_chapter_count: number;
  chapter_word_target: number;
  target_words?: number;
  current_volume?: number;
  current_chapter?: number;
  cover_image?: string;
  initial_idea?: string;
  status: "draft" | "active" | "archived";
  created_at: string;
  updated_at: string;
}

export interface StoryBible {
  id: string;
  project_id: string;
  version: number;
  world_setting: string;
  main_conflict: string;
  themes: string[];
  style_guide?: string;
  narrative_pov: "first_person" | "third_person_limited" | "third_person_omniscient";
  forbidden_elements: string[];
  continuity_rules: string[];
  created_at: string;
  updated_at: string;
}

export interface JobProgress {
  current_step?: string;
  total_steps?: number;
  completed_steps?: number;
  message?: string;
}

export interface GenerationJob {
  id: string;
  project_id: string;
  chapter_id: string | null;
  job_type: "plan_chapters" | string;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled" | string;
  idempotency_key: string;
  model: string;
  progress: JobProgress;
  current_agent?: string;
  result: unknown;
  error: { message: string } | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface ProjectSnapshot {
  project: Project;
  story_bible: StoryBible;
}

export interface Chapter {
  id: string;
  project_id: string;
  volume_no: number;
  chapter_no: number;
  title: string;
  outline: string;
  pov_character: string;
  core_event: string;
  conflict: string;
  turn_point: string;
  emotional_beats: string[];
  plot_purpose: string;
  cliffhanger: string;
  draft_text: string;
  final_text: string;
  summary: string;
  revision_notes: string;
  status: string;
  word_target: number;
  word_count: number;
  sort_order: number;
  is_locked: boolean;
  deleted_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Volume {
  id: string;
  project_id: string;
  volume_no: number;
  title: string;
  outline: string;
  status: string;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface Note {
  id: string;
  project_id: string;
  parent_id: string | null;
  note_type: "note" | "folder" | "inspiration";
  title: string;
  content: string;
  sort_order: number;
  is_pinned: boolean;
  created_at: string;
  updated_at: string;
}

export interface EditorProposal {
  id: string;
  project_id: string;
  chapter_id: string;
  tool_name: string;
  instruction: string;
  original_content: string;
  proposed_content: string;
  diff: string[];
  status: "pending" | "applied" | "rejected";
  created_at: string;
  applied_at: string | null;
}

export interface Character {
  id: string;
  project_id: string;
  name: string;
  aliases: string[];
  role_type: string;
  importance_level: "core" | "major" | "medium" | "minor";
  importance_score: number;
  summary: string;
  appearance: string;
  personality: string;
  goals: string[];
  motivations: string[];
  secrets: string[];
  abilities: string[];
  weaknesses: string[];
  character_arc: string;
  current_status: string;
  related_entity_ids: string[];
  related_character_ids: string[];
  updated_reason: string;
  created_at: string;
  updated_at: string;
}

export interface StoryEntity {
  id: string;
  project_id: string;
  entity_type: string;
  name: string;
  importance_level: string;
  importance_score: number;
  description: string;
  current_status: string;
  source: string;
}

export interface WorldFact {
  id: string;
  project_id: string;
  category: string;
  title: string;
  content: string;
  importance_level: string;
  importance_score: number;
  confidence: number;
  source_chapter_id: string | null;
  related_entity_ids: string[];
}

export interface ForeshadowingItem {
  id: string;
  project_id: string;
  chapter_id: string | null;
  content: string;
  planted_chapter_id: string | null;
  planned_payoff_chapter_id: string | null;
  actual_payoff_chapter_id: string | null;
  planned_payoff: string;
  payoff_status: "planned" | "planted" | "paid_off" | "abandoned" | "candidate";
  importance_level: "core" | "major" | "medium" | "minor";
  importance_score: number;
  related_character_ids: string[];
  related_entity_ids: string[];
  source: "manual" | "agent";
  created_at: string;
  updated_at: string;
}

export interface GraphNode {
  id: string;
  project_id: string;
  node_type: string;
  ref_id: string;
  label: string;
  importance_level: string;
  importance_score: number;
  metadata: Record<string, unknown>;
}

export interface GraphEdge {
  id: string;
  project_id: string;
  source_node_id: string;
  target_node_id: string;
  edge_type: string;
  label: string;
  importance_score: number;
  confidence: number;
  evidence: string;
  metadata: Record<string, unknown>;
}

export interface AgentRun {
  id: string;
  job_id: string;
  project_id: string;
  chapter_id: string | null;
  agent_name: string;
  agent_role: string;
  status: string;
  input_payload: Record<string, unknown>;
  output_payload: Record<string, unknown>;
  error_message: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface LLMProviderOption {
  id: string;
  label: string;
  base_url_env: string;
  api_key_env: string;
  default_model: string;
  notes: string;
}

export interface LLMModelOption {
  id: string;
  provider: string;
  label: string;
  family: string;
  recommended_for: string[];
}

export interface AgentModelConfig {
  id: string;
  workflow_id: string;
  agent_name: string;
  provider: string;
  model: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface AgentConfig {
  name: string;
  role: string;
  order: number;
  prompt: string;
  default_prompt: string;
  is_custom: boolean;
  active_template_id?: string | null;
  prompt_ids?: string[];
  prompt_titles?: Record<string, string>;
  model_configs?: Record<string, AgentModelConfig>;
}

export interface WorkflowNodeSchema {
  title?: string;
  type?: string;
  required?: string[];
  properties?: Record<string, Record<string, unknown>>;
  [key: string]: unknown;
}

export interface WorkflowNode {
  id: string;
  label: string;
  type: "agent" | "control" | "prompt";
  node_subtype?: string;
  agent_name: string | null;
  description: string;
  inputs: string[];
  outputs: string[];
  required_inputs?: string[];
  optional_inputs?: string[];
  produces?: string[];
  input_schema?: WorkflowNodeSchema;
  output_schema?: WorkflowNodeSchema;
  editable: boolean;
  layer: number;
  prompt_id?: string;
  prompt_filename?: string;
  provider?: string | null;
  model?: string | null;
  model_config_id?: string | null;
}

export interface WorkflowEdge {
  source: string;
  target: string;
  label: string;
}

export interface WorkflowDefinition {
  id: string;
  key?: string;
  label: string;
  runtime_status: "active_runtime" | "applied_via_prompt_binding";
  runtime_note: string;
  entrypoints: string[];
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
}

export interface VersionSnapshot {
  id: string;
  project_id: string;
  chapter_id: string | null;
  job_id: string | null;
  agent_name: string;
  content_type: string;
  content: string;
  metadata: Record<string, unknown>;
  user_note: string;
  branch_name: string;
  created_at: string;
}

export interface CreationStarOptionSource {
  name: string;
  url: string;
}

export interface CreationStarOptions {
  channels: string[];
  genres: string[];
  subgenres: string[];
  tags: string[];
  styles: string[];
  target_word_bands: Array<{ label: string; value: number }>;
  sources: CreationStarOptionSource[];
}

export interface CreationStarCard {
  [key: string]: unknown;
  id: string;
  title?: string;
  description?: string;
  tags?: string[];
  genre_mix?: string[];
  core_rule?: string;
  social_pressure?: string;
  power_or_resource_system?: string;
  main_conflict_seed?: string;
  protagonist_entry?: string;
  long_form_potential?: string;
  reader_hooks?: string[];
  selling_point?: string;
  conflict_hook?: string;
  risk?: string;
  revision_hint?: string;
  name?: string;
  identity?: string;
  summary?: string;
  long_term_goal?: string;
  inner_wound?: string;
  ability?: string;
  weakness?: string;
  secret?: string;
  character_arc?: string;
  relationship_hook?: string;
}

export interface CreationStarBasicInfo {
  channel?: string;
  genre?: string;
  subgenres?: string[];
  tags?: string[];
  manual_tags?: string[];
  target_reader?: string;
  target_words?: number;
  style?: string;
  initial_idea?: string;
}

export interface CreationSession {
  id: string;
  project_id: string;
  status: "draft" | "committed" | string;
  current_step: string;
  basic_info: CreationStarBasicInfo;
  state: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface CanonRunPayload {
  worldview: string;
  one_sentence_story: string;
  genre: string;
  target_length: string;
  tone: string;
  reference_works?: string[];
  avoid_elements?: string[];
}

export interface CanonEntity {
  name: string;
  entity_type: string;
  level: "S" | "A" | "B" | "C";
  story_function: string;
  first_appearance: string;
  responsible_agent: string;
  completion_status: "candidate" | "incomplete" | "complete" | "conflict";
  continuity_checked: boolean;
  payload: Record<string, unknown>;
}

export interface DramaNode {
  node_id: string;
  node_type: string;
  title: string;
  description: string;
  story_function: string;
  cost: string;
  state_change: string;
  why_chain: string[];
  related_entities: string[];
}

export interface CanonRunResult {
  project_id: string;
  canon_store_path: string;
  trace_store_path: string;
  version_store_path: string;
  final_outline_path: string;
  final_outline: string;
  continuity_report: { passed: boolean; score: number; issues: Array<Record<string, unknown>> };
  agent_trace: string[];
  drama_nodes: DramaNode[];
  canon_entities: CanonEntity[];
  completion_tickets: Array<Record<string, unknown>>;
  uncertainty_tickets: Array<Record<string, unknown>>;
  agent_handoff_graph: Record<string, string[]>;
}
