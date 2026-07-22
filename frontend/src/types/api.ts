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
  planned_volume_count?: number;
  chapters_per_volume?: number;
  chapter_word_target: number;
  chapter_word_min?: number;
  chapter_word_max?: number;
  target_words?: number;
  current_volume?: number;
  current_chapter?: number;
  cover_image?: string;
  initial_idea?: string;
  status: "draft" | "active" | "archived";
  created_at: string;
  updated_at: string;
}

export interface ScalePlan {
  target_words: number;
  volume_count: number;
  chapter_count: number;
  chapters_per_volume: number;
  chapter_word_target: number;
  chapter_word_min: number;
  chapter_word_max: number;
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
  current_chapter_no?: number;
  child_job_id?: string;
  child_current_step?: string;
  child_step_label?: string;
  child_total_steps?: number;
  child_completed_steps?: number;
  total_chapters?: number;
  completed_chapters?: number;
  overall_percent?: number;
  elapsed_seconds?: number;
  average_chapter_seconds?: number;
  eta_seconds?: number;
  retryable_failed_chapters?: number[];
  long_task?: boolean;
  long_task_advice?: string[];
  message?: string;
}

export interface GenerationJob {
  id: string;
  project_id: string;
  chapter_id: string | null;
  job_type: string;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled" | string;
  idempotency_key: string;
  model: string;
  progress: JobProgress;
  current_agent?: string;
  result: unknown;
  langsmith_run_id?: string;
  langsmith_url?: string;
  trace_mode?: string;
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
  crisis?: string;
  climax?: string;
  outcome?: string;
  chapter_hook?: string;
  foreshadowing_plants?: Record<string, unknown>[];
  foreshadowing_payoffs?: Record<string, unknown>[];
  canon_updates?: Record<string, unknown>[];
  continuity_risks?: Record<string, unknown>[];
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
  note_type: "note" | "folder" | "inspiration" | "import_report" | "method_pack" | "reference_asset" | "review_report";
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
  first_appearance_chapter_id?: string | null;
  last_seen_chapter_id?: string | null;
  related_entity_ids: string[];
  related_character_ids: string[];
  updated_reason: string;
  status?: string;
  source?: string;
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
  first_appearance_chapter_id?: string | null;
  last_seen_chapter_id?: string | null;
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

export type CanonRefType = "character" | "entity" | "world_fact" | "foreshadowing" | "graph_edge" | "folder";

export interface CanonSourceChapter {
  id: string;
  volume_no: number;
  chapter_no: number;
  title: string;
}

export interface CanonHealth {
  official_count: number;
  versioned_count: number;
  unversioned_count: number;
  pending_proposal_count: number;
  low_confidence_count: number;
  conflict_count: number;
  by_type: {
    characters: number;
    entities: number;
    world_facts: number;
    foreshadowing: number;
    graph_edges?: number;
  };
  recommendations: string[];
}

export interface CanonNode {
  id: string;
  project_id: string;
  parent_id: string | null;
  node_type: "folder" | "item";
  ref_type: CanonRefType;
  ref_id: string;
  title: string;
  sort_order: number;
  status: string;
  importance_level: string;
  activity_status: string;
  metadata: Record<string, unknown>;
  content?: Record<string, unknown> | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface CanonVersion {
  id: string;
  project_id: string;
  ref_type: Exclude<CanonRefType, "folder">;
  ref_id: string;
  version_no: number;
  content: Record<string, unknown>;
  source_chapter_id: string | null;
  source_chapter?: CanonSourceChapter | null;
  source_job_id: string | null;
  source_agent: string;
  change_reason: string;
  confidence: number;
  created_at: string;
}

export interface CanonChangeProposal {
  id: string;
  project_id: string;
  target_type: Exclude<CanonRefType, "folder">;
  target_id: string | null;
  operation: string;
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  source_chapter_id: string | null;
  source_chapter?: CanonSourceChapter | null;
  source_job_id: string | null;
  source_agent: string;
  approval_status: "pending" | "approved" | "rejected" | string;
  confidence: number;
  reason: string;
  created_at: string;
  decided_at: string | null;
}

export interface CanonTimelineEvent {
  id: string;
  event_type: "version" | "proposal" | "snapshot" | string;
  ref_type: Exclude<CanonRefType, "folder"> | "chapter";
  ref_id: string | null;
  title: string;
  chapter: CanonSourceChapter | null;
  source_chapter?: CanonSourceChapter | null;
  created_at: string;
  version_no?: number;
  content?: Record<string, unknown>;
  target_type?: Exclude<CanonRefType, "folder">;
  target_id?: string | null;
  operation?: string;
  approval_status?: string;
  source_agent?: string;
  source_job_id?: string | null;
  change_reason?: string;
  reason?: string;
  confidence?: number;
}

export interface CanonTimelineChapter {
  chapter: CanonSourceChapter;
  versions: CanonVersion[];
  proposals: CanonChangeProposal[];
  snapshots: Record<string, unknown>[];
  events: CanonTimelineEvent[];
}

export interface CanonVersionTimeline {
  chapters: CanonTimelineChapter[];
  events: CanonTimelineEvent[];
  unbound: {
    versions: CanonVersion[];
    proposals: CanonChangeProposal[];
    snapshots: Record<string, unknown>[];
    events: CanonTimelineEvent[];
  };
  summary: {
    chapter_count: number;
    event_count: number;
    version_count: number;
    proposal_count: number;
    snapshot_count: number;
  };
  filters: { ref_type: string | null; ref_id: string | null; chapter_id: string | null };
}

export interface CanonImpact {
  ref: { ref_type: string; ref_id: string; title: string; content: Record<string, unknown> };
  chapters: Array<{ id: string; chapter_no: number; title: string; match_reason: string; status: string }>;
  graph: {
    node: GraphNode | null;
    edges: GraphEdge[];
    related_nodes: GraphNode[];
  };
  versions: CanonVersion[];
  proposals: CanonChangeProposal[];
  foreshadowing: ForeshadowingItem[];
  summary: {
    chapter_count: number;
    relation_count: number;
    version_count: number;
    proposal_count: number;
    foreshadowing_count: number;
  };
}

export interface CanonDuplicateScan {
  candidates: Array<{
    source: { ref_type: string; ref_id: string; title: string; content: Record<string, unknown> };
    target: { ref_type: string; ref_id: string; title: string; content: Record<string, unknown> };
    score: number;
    reason: string;
  }>;
  proposals: CanonChangeProposal[];
}

export interface CanonExportPackage {
  filename: string;
  format: "json" | "markdown";
  content: string;
  package: Record<string, unknown> | null;
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
  input?: Record<string, unknown>;
  output?: Record<string, unknown>;
  error_message: string;
  langsmith_run_id?: string;
  langsmith_url?: string;
  trace_mode?: string;
  duration_ms?: number | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface DeepAgentConfig {
  deep_agent: {
    enabled: boolean;
    mode: "advisor" | "orchestrator" | string;
    allow_write: boolean;
    tool_policy: string;
    subagents: string[];
    package: { installed: boolean; version: string };
  };
  langsmith: {
    configured: boolean;
    tracing: boolean;
    project: string;
    endpoint_configured: boolean;
    privacy_mode: "off" | "metadata_only" | "redacted" | "full" | string;
    prompt_sync: "manual" | string;
    package: { installed: boolean; version: string };
  };
}

export interface DeepAgentToolCall {
  id: string;
  session_id: string;
  project_id: string;
  tool_name: string;
  status: "pending_approval" | "approved" | "rejected" | string;
  risk_level: string;
  requires_approval: boolean;
  arguments: Record<string, unknown>;
  result: Record<string, unknown>;
  created_at: string;
  approved_at: string | null;
  rejected_at: string | null;
  executed_at: string | null;
}

export interface DeepAgentSession {
  id: string;
  project_id: string;
  mode: string;
  status: string;
  objective: string;
  privacy_mode: string;
  summary: string;
  state: {
    messages?: Array<Record<string, unknown>>;
    tool_calls?: DeepAgentToolCall[];
    subagents?: string[];
    engine?: string;
    [key: string]: unknown;
  };
  created_at: string;
  updated_at: string;
}

export interface LangSmithStatus {
  configured: boolean;
  tracing: boolean;
  project: string;
  endpoint_configured: boolean;
  privacy_mode: string;
  prompt_sync: string;
  package: { installed: boolean; version: string };
}

export interface LLMProviderOption {
  id: string;
  label: string;
  base_url_env: string;
  api_key_env: string;
  default_model: string;
  notes: string;
  configured?: boolean;
  active?: boolean;
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
  default_agent_name?: string;
  provider?: string | null;
  model?: string | null;
  model_config_id?: string | null;
  configurable?: boolean;
  node_runtime_status?: "configurable_agent" | "prompt_task" | "active_runtime" | "control" | string;
  runtime_note?: string;
  allowed_read_tools?: string[];
  allowed_candidate_tools?: string[];
  validators?: string[];
  forbidden_tools?: string[];
  candidate_policy?: string;
  tags?: string[];
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
  workflow_kind?: "runtime" | "prompt_lifecycle" | "prompt_library" | string;
  trigger_policy?: string;
  tags?: string[];
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
  one_sentence_pitch?: string;
  core_world_rule?: string;
  core_rule?: string;
  social_pressure?: string;
  power_or_resource_system?: string;
  conflict_engine_seed?: string;
  key_entities?: string[];
  rules_not_to_break?: string[];
  protagonist_entry?: string;
  long_form_potential?: string;
  reader_hooks?: string[];
  selling_point?: string;
  conflict_hook?: string;
  writing_risk?: string;
  risk?: string;
  revision_hint?: string;
  difference_from_previous_batch?: string;
  name?: string;
  identity?: string;
  summary?: string;
  opening_situation?: string;
  world_rule_connection?: string;
  long_term_desire?: string;
  long_term_goal?: string;
  immediate_goal?: string;
  inner_wound?: string;
  ability?: string;
  ability_cost?: string;
  weakness?: string;
  secret?: string;
  growth_arc?: string;
  character_arc?: string;
  relationship_hooks?: string[];
  relationship_hook?: string;
  conflict_seed?: string;
  reader_satisfaction?: string;
}

export interface CreationStarBasicInfo {
  channel?: string;
  genre?: string;
  subgenres?: string[];
  tags?: string[];
  manual_tags?: string[];
  target_reader?: string;
  target_words?: number;
  volume_count?: number;
  chapter_count?: number;
  planned_chapter_count?: number;
  chapters_per_volume?: number;
  chapter_word_target?: number;
  chapter_word_min?: number;
  chapter_word_max?: number;
  scale_plan?: ScalePlan;
  style?: string;
  initial_idea?: string;
}

export interface CreationBasicSuggestion {
  id: string;
  target: "initial_idea" | "manual_input";
  title: string;
  content: string;
  tags?: string[];
  reason?: string;
  source?: string;
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

export interface CreationProfileArchive {
  basic_info: CreationStarBasicInfo;
  selected_worldview: Record<string, unknown>;
  selected_protagonist: Record<string, unknown>;
  selected_title: Record<string, unknown>;
  market_position: Record<string, unknown>;
  project_seed: Record<string, unknown>;
  core_conflict_system: Record<string, unknown>;
  novel_constitution: Record<string, unknown>;
  constitution_review: Record<string, unknown>;
  canon_candidates: Record<string, unknown>;
  confirmed_canon: Record<string, unknown>;
}

export interface CreationProjectProfile {
  project: Project;
  story_bible: StoryBible | null;
  creation_session: CreationSession | null;
  creation_profile: CreationProfileArchive;
  profile_summary: {
    has_creation_star: boolean;
    session_status: string;
    session_step: string;
    session_updated_at: string | null;
    canon_sections: string[];
    confirmed: boolean;
  };
}
