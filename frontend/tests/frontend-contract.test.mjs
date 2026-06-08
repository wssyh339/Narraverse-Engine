import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");
const readRoot = (path) => readFileSync(new URL(`../../${path}`, import.meta.url), "utf8");

test("frontend routes match the PRD page list", () => {
  const app = read("src/App.tsx");

  for (const route of [
    "/",
    "/projects/new",
    "/projects/:projectId/workspace",
    "/projects/:projectId/project",
    "/projects/:projectId/outline",
    "/projects/:projectId/notes",
    "/projects/:projectId/agents",
    "/projects/:projectId/versions",
    "/projects/:projectId/characters",
    "/projects/:projectId/graph",
    "/projects/:projectId/world",
    "/projects/:projectId/foreshadowing",
    "/projects/:projectId/batch",
    "/projects/:projectId/export",
    "/jobs/:jobId",
  ]) {
    assert.match(app, new RegExp(route.replace(/[/:]/g, "\\$&")));
  }
});

test("project studio exposes five connected creation workspaces", () => {
  const layout = read("src/layouts/StudioLayout.tsx");
  const agents = read("src/pages/AgentsPage.tsx");

  for (const label of ["作品", "正文", "设定", "大纲", "笔记"]) {
    assert.match(layout, new RegExp(label));
  }
  assert.ok(layout.indexOf('label: "创作 Star"') < layout.indexOf('label: "作品"'));
  assert.match(layout, /CreationStarWizard/);
  assert.match(layout, /专注写作|focus/i);
  assert.match(layout, /自动保存/);
  assert.match(agents, /activeWorkflow\.nodes\.map/);
  assert.match(agents, /打开节点配置/);
});

test("workbench API supports directory, notes, proposals, versions, and backup", () => {
  const studio = read("src/api/studio.ts");

  for (const endpoint of [
    "/volumes",
    "/chapters/reorder",
    "/chapters/trash",
    "/notes",
    "/proposals",
    "/snapshot",
    "/backup",
  ]) {
    assert.match(studio, new RegExp(endpoint.replace(/[/:]/g, "\\$&")));
  }
});

test("frontend API modules use only MVP backend endpoints", () => {
  const projects = read("src/api/projects.ts");
  const chapters = read("src/api/chapters.ts");
  const jobs = read("src/api/jobs.ts");

  assert.match(projects, /\/projects/);
  assert.match(projects, /\/story-bible/);
  assert.match(chapters, /\/chapters\/plan/);
  assert.match(jobs, /\/jobs\/\$\{jobId\}/);
});

test("pages expose loading, empty, and error states", () => {
  const source = [
    read("src/pages/ProjectListPage.tsx"),
    read("src/pages/ProjectWorkspacePage.tsx"),
    read("src/pages/StoryBiblePage.tsx"),
    read("src/pages/ChapterPlanPage.tsx"),
    read("src/pages/JobDetailPage.tsx"),
  ].join("\n");

  assert.match(source, /加载中|正在/);
  assert.match(source, /暂无|还没有|请先创建项目/);
  assert.match(source, /出错|失败|无法|错误/);
});

test("deployment files document startup and expose required scripts", () => {
  const packageJson = JSON.parse(read("package.json"));
  const readme = readRoot("README.md");

  for (const script of ["dev", "build", "start"]) {
    assert.equal(typeof packageJson.scripts?.[script], "string");
  }
  assert.match(readme, /安装|install/i);
  assert.match(readme, /启动|start|dev/i);
  assert.match(readme, /核心能力|功能|feature/i);
});

test("project creation and dashboard protect repeated actions and expose friendly errors", () => {
  const wizard = read("src/pages/ProjectCreateWizard.tsx");
  const dashboard = read("src/pages/DashboardPage.tsx");

  assert.match(wizard, /CreationStarWizard/);
  assert.match(wizard, /开始创作 Star/);
  assert.match(wizard, /nextInFlightRef\.current/);
  assert.match(wizard, /创建项目失败/);
  assert.match(wizard, /openStar/);
  assert.match(dashboard, /creationStar=1/);
  assert.match(dashboard, /Modal\.confirm/);
  assert.match(dashboard, /无法连接后端服务/);
  assert.match(dashboard, /deleteMutation\.isPending/);

  const layout = read("src/layouts/StudioLayout.tsx");
  assert.match(layout, /recent-workspace/);
  assert.match(layout, /recent-settings/);
});

test("workspace exposes loading, empty, error, generation, and foreshadowing controls", () => {
  const workspace = read("src/pages/WorkspacePage.tsx");
  const wizard = read("src/components/CreationStarWizard.tsx");
  const studio = read("src/api/studio.ts");

  assert.match(workspace, /stateQuery\.isLoading/);
  assert.match(workspace, /stateQuery\.error/);
  assert.match(workspace, /还没有章节|暂无/);
  assert.match(workspace, /proposalMutation\.isPending/);
  assert.match(workspace, /AI 提案已生成，确认后才会写入正文/);
  assert.match(workspace, /预埋伏笔/);
  assert.match(workspace, /回收伏笔/);
  assert.match(workspace, /Agent 建议伏笔/);
  assert.doesNotMatch(workspace, /<Button type="primary" icon=\{<Star/);
  assert.match(workspace, /智能排版/);
  assert.match(workspace, /查找替换/);
  assert.match(workspace, /高频词/);
  assert.match(workspace, /历史版本/);
  assert.match(workspace, /AI 协作助手/);
  assert.match(workspace, /应用提案/);
  assert.match(workspace, /title="AI 提案预览"/);
  assert.doesNotMatch(workspace, /创作 Star/);
  assert.doesNotMatch(workspace, /<CreationStarWizard/);
  assert.match(studio, /\/creation-star\/options/);
  assert.match(studio, /\/creation-star\/draw/);
  assert.match(studio, /\/creation-star\/commit/);
  for (const label of ["基本信息", "世界观抽卡", "主角人设", "总设定表", "创建书名", "完成创建"]) {
    assert.match(wizard, new RegExp(label));
  }
  assert.match(wizard, /step: "title"/);
  assert.match(wizard, /selected_title/);
  assert.match(wizard, /customTitle/);
  assert.match(wizard, /自定义书名/);
  assert.match(wizard, /使用自定义书名/);
  assert.match(wizard, /prompt_snapshot/);
});

test("workspace exposes streaming assistant chat for selected chapter text", () => {
  const workspace = read("src/pages/WorkspacePage.tsx");
  const studio = read("src/api/studio.ts");

  assert.match(studio, /chat\/stream/);
  assert.match(workspace, /streamChapterChat/);
  assert.match(workspace, /assistant-ui/);
  assert.match(workspace, /选区上下文/);
  assert.match(workspace, /应用到选区/);
  assert.match(workspace, /生成提案 → 展示差异 → 用户确认 → 应用前快照 → 写入正文/);
});

test("outline studio exposes long-novel planning controls", () => {
  const outline = read("src/pages/OutlineStudioPage.tsx");
  const outlineDirectory = read("src/pages/outline/OutlineDirectory.tsx");
  const outlineEditor = read("src/pages/outline/OutlineEditorPanel.tsx");
  const outlineGraph = read("src/pages/outline/OutlineInferenceGraph.tsx");
  const outlineModal = read("src/pages/outline/OutlineGenerationModal.tsx");
  const outlineCanon = read("src/pages/outline/CanonStudioPanel.tsx");
  const outlineUtils = read("src/pages/outline/outlineUtils.tsx");
  const studio = read("src/api/studio.ts");
  const outlineBundle = [outline, outlineDirectory, outlineEditor, outlineGraph, outlineModal, outlineCanon].join("\n");

  for (const label of ["生成大纲", "生成卷纲", "生成章纲", "基本信息", "世界观", "主角", "额外自定义输入", "真实 Agent 推演链", "总纲", "卷纲", "章节", "章纲"]) {
    assert.match(outlineBundle, new RegExp(label));
  }
  assert.match(outlineBundle, /target_words/);
  assert.match(outlineBundle, /volume_count/);
  assert.match(outlineBundle, /chapters_per_volume/);
  assert.match(outlineBundle, /chapter_word_target/);
  assert.match(outline, /outlinePreviewOpen/);
  assert.match(outline, /App\.useApp/);
  assert.doesNotMatch(outline, /Modal\.confirm/);
  assert.match(outline, /inferenceSteps/);
  assert.match(outline, /outline_swarm/);
  assert.match(`${outline}\n${outlineUtils}`, /agent_trace/);
  assert.doesNotMatch(outlineUtils, /OUTLINE_AGENT_STEPS/);
  assert.match(outline, /computedTargetWords/);
  assert.match(outlineModal, /OutlineInferenceGraph/);
  assert.match(outline, /OutlineDirectory/);
  assert.match(outline, /OutlineEditorPanel/);
  assert.match(outline, /OutlineGenerationModal/);
  assert.match(outline, /CanonStudioPanel/);
  assert.ok(outline.split("\n").length < 430, "OutlineStudioPage should remain an orchestrator, not a monolith");
  assert.match(outlineGraph, /outline-agent-graph/);
  assert.match(outlineGraph, /等待后端返回真实推演记录/);
  assert.doesNotMatch(outline, /window\.setInterval/);
  assert.doesNotMatch(outline, /OUTLINE_AGENT_STEPS\.map/);
  assert.doesNotMatch(outlineBundle, /13Agent推演链/);
  assert.match(outline, /selectedChapterIds/);
  assert.match(outline, /sameStringArray/);
  assert.match(outlineDirectory, /批量管理/);
  assert.match(outlineDirectory, /batchManagementEnabled/);
  assert.match(outlineBundle, /批量删除/);
  assert.match(outlineBundle, /删除总纲/);
  assert.match(outlineBundle, /删除卷纲/);
  assert.match(outline, /deleteSelectedChapters/);
  assert.match(outline, /confirmClearOutline/);
  assert.match(outline, /confirmDeleteVolume/);
  assert.match(outline, /generateFromExistingOutline/);
  assert.match(outline, /请先生成总纲/);
  assert.match(outlineDirectory, /renderVolumeChapterTree/);
  assert.match(outlineDirectory, /outline-directory-bulk-actions/);
  assert.match(outlineDirectory, /批量管理[\s\S]*删除总纲/);
  assert.match(outlineDirectory, /outline-volume-group/);
  assert.match(outlineDirectory, /outline-nested-chapters/);
  assert.doesNotMatch(outlineDirectory, /outline-trash/);
  assert.doesNotMatch(outlineDirectory, /回收站/);
  assert.doesNotMatch(outline, /回收站/);
  assert.match(outline, /toggleDirectorySelection/);
  assert.match(outlineEditor, /openGenerationPreview/);
  assert.match(outlineEditor, /generateFromExistingOutline/);
  assert.doesNotMatch(outlineEditor, /openGenerationPreview\\("volume"\\)/);
  assert.doesNotMatch(outlineEditor, /openGenerationPreview\\("chapter"\\)/);
  assert.doesNotMatch(outlineEditor, /删除总纲|删除大纲|删除卷纲|删除章纲/);
  assert.match(outlineEditor, /formatOutlineDocument/);
  assert.match(outlineEditor, /outline-prose/);
  assert.doesNotMatch(outlineEditor, /readableJson/);
  assert.match(outlineModal, /generationStarted/);
  assert.doesNotMatch(outlineCanon, /正典补全/);
  assert.doesNotMatch(outlineCanon, /长篇小说多 Agent 协作推演与正典补全系统/);
  assert.match(studio, /deleteVolume/);
  assert.match(studio, /\/volumes\/\$\{volumeId\}/);
  assert.match(studio, /chapters\/trash\/batch/);
  assert.doesNotMatch(outline, /outline-generate-actions/);
  assert.doesNotMatch(outline, />\\s*起始章节\\s*</);
  assert.doesNotMatch(outline, />\\s*本次生成章纲数\\s*</);
  assert.doesNotMatch(outline, /setOutlinePreviewOpen\\(false\\);\\s*setSelectedView/);
  assert.match(studio, /outline_plan/);
});

test("outline studio hides inline canon completion panel content", () => {
  const outline = read("src/pages/OutlineStudioPage.tsx");
  const outlineCanon = read("src/pages/outline/CanonStudioPanel.tsx");
  const studio = read("src/api/studio.ts");

  assert.match(outline, /CanonStudioPanel/);
  assert.match(outlineCanon, /return null/);
  for (const label of ["正典补全", "世界观输入框", "一句话故事输入框", "Agent handoff", "正典库实体表", "实体补全状态表", "DramaNode 故事节点图", "ContinuityAgent 审查结果", "final_outline.md", "canon_store.json"]) {
    assert.doesNotMatch(outlineCanon, new RegExp(label));
  }
  assert.doesNotMatch(outlineCanon, /runCanonStudio/);
  assert.doesNotMatch(outlineCanon, /downloadCanonArtifact/);
  assert.match(studio, /canon-studio\/run/);
  assert.match(studio, /canon-studio\/store/);
  assert.match(studio, /canon-studio\/final-outline/);
});

test("docs describe the split API and outline frontend structure", () => {
  const readme = readRoot("README.md");
  const codex = readRoot("Codex.md");

  for (const doc of [readme, codex]) {
    assert.match(doc, /backend\/app\/api\/v1\/endpoints\/project_studio\.py/);
    assert.match(doc, /backend\/app\/api\/v1\/endpoints\/knowledge\.py/);
    assert.match(doc, /backend\/app\/api\/v1\/endpoints\/writing\.py/);
    assert.match(doc, /frontend\/src\/pages\/outline\//);
    assert.match(doc, /OutlineStudioPage/);
  }
});

test("version management exposes compare and rollback actions", () => {
  const versions = read("src/pages/VersionsPage.tsx");

  assert.match(versions, /compareVersions/);
  assert.match(versions, /rollbackVersion/);
  assert.match(versions, /Modal\.confirm/);
  assert.match(versions, /回滚成功/);
});

test("batch page exposes real job status and control actions", () => {
  const batch = read("src/pages/BatchPage.tsx");
  const studio = read("src/api/studio.ts");

  assert.match(batch, /setJob\(result\.job\)/);
  assert.match(batch, /暂停/);
  assert.match(batch, /恢复/);
  assert.match(batch, /取消/);
  assert.doesNotMatch(batch, /mutation\.isPending \? 45/);
  assert.match(studio, /\/write\/pause/);
  assert.match(studio, /\/write\/resume/);
  assert.match(studio, /\/write\/cancel/);
});

test("job page renders readable outline swarm agent run details", () => {
  const job = read("src/pages/JobPage.tsx");

  for (const label of ["LLM 来源", "本地降级", "Swarm Trace", "迭代次数", "原始载荷"]) {
    assert.match(job, new RegExp(label));
  }
  assert.match(job, /isOutlineSwarmRun/);
  assert.match(job, /renderAgentRunDetails/);
  assert.match(job, /trace_events/);
  assert.match(job, /outline_swarm/);
  assert.doesNotMatch(job, /JSON\.stringify\(run\.output_payload, null, 2\)\.slice\(0, 500\)/);
});

test("Ant Design application context wraps pages that use App.useApp", () => {
  const app = read("src/App.tsx");

  assert.match(app, /App as AntdApp/);
  assert.match(app, /<AntdApp>/);
});
