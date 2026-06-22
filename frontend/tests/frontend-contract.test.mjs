import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
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
    "/projects/:projectId/settings",
    "/projects/:projectId/settings/tree",
    "/projects/:projectId/settings/profile",
    "/projects/:projectId/settings/characters",
    "/projects/:projectId/settings/world",
    "/projects/:projectId/settings/graph",
    "/projects/:projectId/settings/foreshadowing",
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
  const app = read("src/App.tsx");
  const agents = read("src/pages/AgentsPage.tsx");

  for (const label of ["创作 Star", "大纲", "设定", "正文", "Agent"]) {
    assert.match(layout, new RegExp(label));
  }
  const primaryBlock = layout.slice(layout.indexOf("const primaryItems"), layout.indexOf("const handleProjectMenuClick"));
  const toolBlock = layout.slice(layout.indexOf("const toolItems"), layout.indexOf("if (isProjectStudio)"));
  assert.doesNotMatch(primaryBlock, /label: "作品"/);
  assert.doesNotMatch(primaryBlock, /label: "笔记"/);
  assert.ok(primaryBlock.indexOf('label: "创作 Star"') < primaryBlock.indexOf('label: "大纲"'));
  assert.ok(primaryBlock.indexOf('label: "大纲"') < primaryBlock.indexOf('label: "设定"'));
  assert.ok(primaryBlock.indexOf('label: "设定"') < primaryBlock.indexOf('label: "正文"'));
  assert.ok(primaryBlock.indexOf('label: "正文"') < primaryBlock.indexOf('label: "Agent"'));
  for (const label of ["批量", "笔记", "导出", "版本"]) {
    assert.match(toolBlock, new RegExp(label));
  }
  for (const label of ["图谱", "世界", "伏笔"]) {
    assert.doesNotMatch(toolBlock, new RegExp(`label: "${label}"`));
  }
  assert.match(layout, /isWorkspacePath/);
  assert.match(layout, /settings\/tree/);
  assert.match(app, /ProjectSettingsSectionRedirect section="profile"/);
  assert.match(layout, /CreationStarWizard/);
  assert.match(layout, /专注写作|focus/i);
  assert.match(layout, /自动保存/);
  assert.match(layout, /listLlmModels/);
  assert.match(layout, /LLM 未配置/);
  assert.match(layout, /configuration_warning/);
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
    "/settings/tree",
    "/settings/health",
    "/settings/folders",
    "/settings/nodes",
    "/settings/proposals",
    "/settings/duplicates/scan",
    "/settings/export",
    "/settings/version-timeline",
    "/creation/profile",
    "/locks",
    "/impact",
    "/settings/archive",
  ]) {
    assert.match(studio, new RegExp(endpoint.replace(/[/:]/g, "\\$&")));
  }
});

test("frontend API modules use only MVP backend endpoints", () => {
  const projects = read("src/api/projects.ts");
  const studio = read("src/api/studio.ts");
  const jobs = read("src/api/jobs.ts");
  const app = read("src/App.tsx");
  const deletedLegacyFiles = [
    "src/api/chapters.ts",
    "src/pages/ChapterPlanPage.tsx",
    "src/pages/ProjectWorkspacePage.tsx",
    "src/components/AppShell.tsx",
  ];

  assert.match(projects, /\/projects/);
  assert.match(projects, /\/story-bible/);
  assert.match(jobs, /\/jobs\/\$\{jobId\}/);
  assert.doesNotMatch(studio, /chapters\/plan|planChapters/);
  assert.doesNotMatch(app, /chapters\/plan|ChapterPlanPage|ProjectWorkspacePage|AppShell/);
  for (const deletedPath of deletedLegacyFiles) {
    assert.equal(existsSync(new URL(`../${deletedPath}`, import.meta.url)), false, `${deletedPath} should stay deleted`);
  }
});

test("pages expose loading, empty, and error states", () => {
  const source = [
    read("src/pages/ProjectListPage.tsx"),
    read("src/pages/WorkspacePage.tsx"),
    read("src/pages/OutlineStudioPage.tsx"),
    read("src/pages/JobPage.tsx"),
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

test("local startup is driven by the root env file", () => {
  const packageJson = JSON.parse(read("package.json"));
  const readme = readRoot("README.md");
  const envExample = readRoot(".env.example");
  const compose = readRoot("docker-compose.yml");
  const viteConfig = read("vite.config.ts");
  const backendScriptUrl = new URL("../../scripts/dev-backend.sh", import.meta.url);
  const frontendScriptUrl = new URL("../../scripts/dev-frontend.sh", import.meta.url);

  assert.equal(existsSync(backendScriptUrl), true);
  assert.equal(existsSync(frontendScriptUrl), true);
  const backendScript = readRoot("scripts/dev-backend.sh");
  const frontendScript = readRoot("scripts/dev-frontend.sh");

  for (const entry of [
    "BACKEND_HOST=0.0.0.0",
    "BACKEND_PORT=8000",
    "FRONTEND_HOST=0.0.0.0",
    "FRONTEND_PORT=5173",
    "DATABASE_URL=sqlite:///./data/novel_agent.db",
    "JOB_ARTIFACT_DIR=artifacts/runs",
    "VITE_API_BASE_URL=http://localhost:8000/api",
  ]) {
    assert.match(envExample, new RegExp(entry.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  }

  assert.match(backendScript, /source "\$ROOT_DIR\/\.env"/);
  assert.match(backendScript, /BACKEND_HOST/);
  assert.match(backendScript, /BACKEND_PORT/);
  assert.match(backendScript, /uvicorn --app-dir backend app\.main:app/);
  assert.match(frontendScript, /source "\$ROOT_DIR\/\.env"/);
  assert.match(frontendScript, /VITE_API_BASE_URL/);
  assert.match(frontendScript, /pnpm.*dev/);

  assert.match(readme, /\.\/scripts\/dev-backend\.sh/);
  assert.match(readme, /\.\/scripts\/dev-frontend\.sh/);
  assert.doesNotMatch(readme, /DATABASE_URL=sqlite:\/\/\/\.\/backend\/data\/novel_agent\.db/);
  assert.doesNotMatch(readme, /VITE_API_BASE_URL=http:\/\/localhost:8000\/api pnpm dev/);

  assert.match(compose, /DATABASE_URL: \$\{DATABASE_URL:-sqlite:\/\/\/\.\/data\/novel_agent\.db\}/);
  assert.match(compose, /JOB_ARTIFACT_DIR: \$\{JOB_ARTIFACT_DIR:-artifacts\/runs\}/);
  assert.match(compose, /FRONTEND_ORIGIN: \$\{FRONTEND_ORIGIN:-http:\/\/localhost:5173\}/);
  assert.match(compose, /VITE_API_BASE_URL: \$\{VITE_API_BASE_URL:-http:\/\/localhost:8000\/api\}/);

  assert.equal(packageJson.scripts.dev, "vite");
  assert.equal(packageJson.scripts.start, "vite preview");
  assert.match(viteConfig, /loadEnv/);
  assert.match(viteConfig, /envDir: "\.\."/);
  assert.match(viteConfig, /FRONTEND_HOST/);
  assert.match(viteConfig, /FRONTEND_PORT/);
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
  assert.match(dashboard, /App\.useApp/);
  assert.doesNotMatch(dashboard, /Typography, message/);

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
  for (const label of ["基本信息", "世界观抽卡", "主角人设", "书名与包装", "核心与宪法", "完成创建"]) {
    assert.match(wizard, new RegExp(label));
  }
  for (const removedStep of ["立项种子", "压力测试", "正典预览"]) {
    assert.doesNotMatch(wizard, new RegExp(`title: "${removedStep}"`));
  }
  assert.doesNotMatch(wizard, /总设定表|创建书名/);
  assert.match(wizard, /title_packaging/);
  assert.match(wizard, /selected_title/);
  assert.doesNotMatch(wizard, /customTitle/);
  assert.doesNotMatch(wizard, /自定义书名/);
  assert.doesNotMatch(wizard, /使用自定义书名/);
  assert.match(wizard, /prompt_snapshot/);
  assert.match(studio, /replace_existing/);
  assert.match(studio, /approved_canon_sections/);
  assert.match(wizard, /name="target_reader"/);
  assert.match(wizard, /目标读者体验/);
  assert.match(wizard, /爽感、压迫感、宿命感、成长感、权谋感、情感拉扯、史诗感/);
  assert.doesNotMatch(wizard, /label="目标读者"/);
  assert.match(wizard, /DRAW_BATCH_SIZE = 3/);
  assert.match(wizard, /loadProgressiveCardBatch/);
  assert.match(wizard, /Promise\.all/);
  assert.match(wizard, /count: 1/);
  assert.match(wizard, /加载三张世界观/);
  assert.match(wizard, /刷新三张世界观/);
  assert.match(wizard, /加载三张主角/);
  assert.match(wizard, /刷新三张主角/);
  assert.match(wizard, /加载三张书名包装/);
  assert.match(wizard, /刷新三张书名包装/);
  assert.match(wizard, /完成一张显示一张|完成一个显示一个/);
  assert.doesNotMatch(wizard, /count: DRAW_BATCH_SIZE/);
  assert.doesNotMatch(wizard, /加载一张世界观|加载一张主角|加载一个方向/);

  for (const field of [
    "channel",
    "genre",
    "subgenres",
    "tags",
    "manual_tags",
    "target_reader",
    "volume_count",
    "chapter_count",
    "chapter_word_min",
    "chapter_word_max",
    "target_words",
    "style",
    "initial_idea",
  ]) {
    assert.match(wizard, new RegExp(`name="${field}"`));
  }
  assert.match(wizard, /Scale Planner/);
  assert.match(wizard, /computedTargetWords/);
  assert.match(wizard, /chapter_word_target/);
  assert.match(wizard, /label="每章字数"/);
  assert.doesNotMatch(wizard, /label="每章最少字数"/);
  assert.doesNotMatch(wizard, /label="每章最多字数"/);
  assert.doesNotMatch(wizard, /每章字数范围/);
  assert.match(wizard, /总字数不可手动填写/);
  assert.doesNotMatch(wizard, /<Select options=\{targetWordOptions\} placeholder="选择目标字数带" \/>/);
  for (const marker of [
    "creation-star-brief-shell",
    "creation-star-brief-header",
    "creation-star-basic-section",
    "creation-star-ai-suggestion-grid",
    "creation-star-flow-checklist",
    "后续流程读取",
    "创作种子",
    "targetReaderOptions",
    "targetWordOptions",
    "TARGET_READER_PRESETS",
    "target_word_bands",
    "generateCreationBasicSuggestions",
    "basicSuggestionMutation",
    "刷新 AI 选项",
    "应用到初始想法",
    "应用到额外约束",
    "appendManualConstraint",
  ]) {
    assert.ok(wizard.includes(marker), `missing marker: ${marker}`);
  }
  assert.doesNotMatch(wizard, /IDEA_PRESETS/);
  assert.doesNotMatch(wizard, /MANUAL_CONSTRAINT_PRESETS/);
  assert.doesNotMatch(wizard, /renderTargetWordPresets/);
  assert.match(studio, /creation\/basic-suggestions/);
});

test("outline debate header exposes compact scale planner summary", () => {
  const panel = read("src/pages/outline/OutlineDebatePanel.tsx");
  const page = read("src/pages/OutlineStudioPage.tsx");

  assert.match(page, /targetWords=\{debateScalePlan\.target_words\}/);
  assert.match(panel, /outline-debate-scale-summary/);
  assert.match(panel, /总字数/);
  assert.match(panel, /卷章/);
  assert.match(panel, /单章/);
  assert.doesNotMatch(panel, /Scale Planner：/);
});

test("batch monitor exposes long-running progress and retry context", () => {
  const page = read("src/pages/BatchPage.tsx");
  const types = read("src/types/api.ts");

  for (const field of [
    "overall_percent?: number",
    "elapsed_seconds?: number",
    "eta_seconds?: number",
    "average_chapter_seconds?: number",
    "retryable_failed_chapters?: number[]",
    "long_task_advice?: string[]",
  ]) {
    assert.match(types, new RegExp(field.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  }
  for (const label of ["overallPercent", "当前章节进度", "预计剩余", "长篇任务建议", "可重试章节"]) {
    assert.match(page, new RegExp(label));
  }
});

test("outline studio keeps body visibility independent from directory selection", () => {
  const page = read("src/pages/OutlineStudioPage.tsx");
  const directory = read("src/pages/outline/OutlineDirectory.tsx");
  const debate = read("src/pages/outline/OutlineDebatePanel.tsx");

  assert.match(page, /openDirectoryView/);
  assert.match(page, /setSelectedView\(view\)/);
  assert.match(page, /nextMissingChapterNo/);
  assert.match(page, /nextDebateChapterNo/);
  assert.match(page, /selectedChapter\?\.chapter_no \?\? nextDebateChapterNo/);
  assert.doesNotMatch(page, /setSelectedView\(view\);\s*setDetailOpen\(true\)/);
  assert.match(page, /selectedView=\{selectedView\}/);
  assert.match(page, /onPhaseComplete=\{invalidate\}/);
  assert.match(debate, /selectedView\?: OutlineView/);
  assert.match(debate, /selectedView === "volume"/);
  assert.match(debate, /selectedView === "chapterOutline"/);
  assert.match(debate, /lastSelectedViewRef/);
  assert.match(debate, /selectedView === lastSelectedViewRef\.current/);
  assert.match(debate, /onPhaseComplete\?\.\(confirmedRun\)/);
  assert.match(debate, /phaseFullyConfirmed/);
  assert.match(debate, /phaseStatus\(session, "chapters", phaseFullyConfirmed\("chapters"\)\)/);
  assert.match(debate, /scalePlan\?\.chapter_count/);
  assert.match(debate, /confirmedCount >= expectedCount/);
  assert.match(debate, /confirmedRefreshBlocked/);
  assert.match(debate, /activeItemAlreadyConfirmed/);
  assert.match(directory, /aria-pressed=\{detailOpen\}/);
  assert.match(directory, /隐藏大纲正文|显示大纲正文/);
});

test("outline body renders structured debate content with localized labels", () => {
  const editor = read("src/pages/outline/OutlineEditorPanel.tsx");

  for (const marker of [
    "safeParseStructuredText",
    "normalizePythonLikeJson",
    "extractStructuredOutlineSections",
    "outlineFieldLabels",
    "phase_3: \"阶段三\"",
    "stage_goal: \"阶段目标\"",
    "main_conflict: \"主线冲突\"",
    "boundary: \"边界选择\"",
    "cost: \"代价\"",
    "chapters: \"章节范围\"",
  ]) {
    assert.ok(editor.includes(marker), `missing marker: ${marker}`);
  }

  assert.doesNotMatch(editor, /replace\(\/_\/g, " "\)/);
});

test("creation star title packaging is a single editable card lane without separate market cards", () => {
  const wizard = read("src/components/CreationStarWizard.tsx");

  for (const marker of [
    "书名与包装",
    "loadTitlePackaging",
    "loadTitlePackagingBatch",
    "titlePackagingBatchLoading",
    "renderTitlePackaging",
    "core_selling_point",
    "reader_expectation",
    "platform_style",
    "one_sentence_ad",
    "worldview_hook",
    "protagonist_hook",
    "标题包装生成失败",
    "下一步",
  ]) {
    assert.ok(wizard.includes(marker), `missing marker: ${marker}`);
  }

  for (const removed of [
    "marketCards",
    "selectedMarketId",
    "selectedMarket",
    "updateMarket",
    "renderMarketPosition",
    "loadMarketPositionBatch",
    "marketBatchLoading",
    "市场定位",
    "market_position_candidates ??",
  ]) {
    assert.doesNotMatch(wizard, new RegExp(removed));
  }

  assert.match(wizard, /market_position:\s*buildMarketPositionFromTitle\(selectedTitle/);
});

test("creation star seed preview localizes structured field labels", () => {
  const wizard = read("src/components/CreationStarWizard.tsx");

  assert.match(wizard, /CREATION_STAR_FIELD_LABELS/);
  assert.match(wizard, /labelForKey/);
  assert.match(wizard, /<strong>\{labelForKey\(key\)\}：<\/strong>/);
  assert.doesNotMatch(wizard, /<strong>\{key\}：<\/strong>/);

  for (const marker of [
    'target_reader: "目标读者"',
    'platform_fit: "平台风格"',
    'selling_point: "卖点"',
    'core_selling_point: "核心卖点"',
    'basic_positioning: "小说基本定位"',
    'core_narrative_engine: "核心叙事发动机"',
    'protagonist_arc: "主角轨迹"',
    'world_rules: "世界规则"',
    'character_functions: "主要人物功能"',
    'theme_pressure: "主题压力"',
    'reader_expectation: "读者期待"',
    'session_id: "会话 ID"',
    'current_step: "当前步骤"',
    'story_bible_candidate: "Story Bible 候选"',
  ]) {
    assert.ok(wizard.includes(marker), `missing marker: ${marker}`);
  }

  assert.match(wizard, /renderDisplayValue/);
  assert.match(wizard, /hasDisplayValue/);
  assert.match(wizard, /typeof value === "object"/);
  assert.match(wizard, /renderKeyValues\(record\(value\)\)/);
  assert.doesNotMatch(wizard, /<strong>\{labelForKey\(key\)\}：<\/strong>\{displayValue\(key, value\)\}/);
});

test("creation star removes seed review and canon preview stages from the wizard", () => {
  const wizard = read("src/components/CreationStarWizard.tsx");

  for (const removed of [
    "renderSeed",
    "renderConstitutionReview",
    "renderCanonPreview",
    "enterSeed",
    "enterConstitutionReview",
    "enterCanonPreview",
    "enterFinalConfirm",
    "确认立项种子",
    "生成压力测试",
    "生成正典预览",
    "正典审批项",
    "已选世界观完整字段",
    "已选主角完整字段",
    "已选书名包装完整字段",
    "renderKeyValues(record(selectedWorldview",
    "renderKeyValues(record(selectedProtagonist",
    "renderKeyValues(record(selectedTitle",
  ]) {
    assert.ok(!wizard.includes(removed), `unexpected seed preview marker: ${removed}`);
  }
});

test("creation star core and constitution are editable with localized fields", () => {
  const wizard = read("src/components/CreationStarWizard.tsx");

  for (const marker of [
    "renderEditableKeyValues",
    "updateCoreConflictField",
    "updateNovelConstitutionField",
    "core_conflict_system: coreConflict",
    "novel_constitution: novelConstitution",
    "conflict_engine_seed",
    'protagonist_desire: "主角欲望"',
    'world_resistance: "世界阻力"',
    'core_conflict: "核心矛盾"',
    'external_resistance: "外部阻力"',
    'internal_resistance: "内部阻力"',
    'relationship_resistance: "关系阻力"',
    'institutional_resistance: "制度阻力"',
    'typical_cost: "典型代价"',
    'long_form_engine: "长篇发动机"',
    'possible_endpoint: "可能终点"',
    'theme_question: "主题问题"',
    'basic_positioning: "小说基本定位"',
    'core_narrative_engine: "核心叙事发动机"',
    'protagonist_arc: "主角轨迹"',
    'world_rules: "世界规则"',
    'character_functions: "主要人物功能"',
    'theme_pressure: "主题压力"',
    'cost_mechanism: "代价机制"',
    'forbidden_directions: "禁区"',
    'long_form_sustainability: "长篇可持续性"',
  ]) {
    assert.ok(wizard.includes(marker), `missing marker: ${marker}`);
  }

  assert.doesNotMatch(wizard, /renderKeyValues\(coreConflict\)/);
  assert.doesNotMatch(wizard, /renderKeyValues\(novelConstitution\)/);
});

test("creation star footer only navigates while generation uses project cache and progressive card requests", () => {
  const wizard = read("src/components/CreationStarWizard.tsx");

  for (const marker of [
    "useEffect",
    "formatElapsedTime",
    "useElapsedSeconds",
    "GenerationTimer",
    "generation-timer",
    "用时",
    "worldviewGenerationActive",
    "protagonistGenerationActive",
    "titlePackagingGenerationActive",
    "coreConstitutionGenerationActive",
    "basicSuggestionMutation.isPending",
    "GenerationTimer active={worldviewGenerationActive}",
    "GenerationTimer active={protagonistGenerationActive}",
    "GenerationTimer active={titlePackagingGenerationActive}",
    "GenerationTimer active={coreConstitutionGenerationActive}",
    "GenerationTimer active={basicSuggestionMutation.isPending}",
    "creationStarProjectCacheKey",
    "loadCachedCreationStar",
    "saveCreationStarCache",
    "localStorage",
    "count: 1",
    "loadProgressiveCardBatch",
    "Promise.all",
    "ensureCreationSession",
    "ensureProjectSeed",
    "previousCreationStep",
    "nextCreationStep",
    "上一步",
    "下一步",
    "worldviewBatchTokenRef",
    "protagonistBatchTokenRef",
    "titlePackagingBatchTokenRef",
    "createCardSkeleton",
    "applyGeneratedCard",
    "stableId",
    "source_card_id",
    "cacheGeneratedCards",
    "seenIds",
    "cached-card-",
    "AntApp.useApp",
    "本次生成未返回有效卡片",
    "本轮只生成",
    "确认已选世界观、主角和书名包装卡后",
    "renderEditableText",
    "renderEditableList",
    "生成中",
  ]) {
    assert.ok(wizard.includes(marker), `missing marker: ${marker}`);
  }

  assert.match(wizard, /App as AntApp/);
  assert.match(wizard, /applyGeneratedCard\(card, \(patch\) => patchCard\(skeleton\.id, patch\), skeleton\.id\)/);
  assert.doesNotMatch(wizard, /Typography,\s*message\s*}/);
  assert.doesNotMatch(wizard, /逐字生成/);
  assert.doesNotMatch(wizard, /revealCardText/);
  assert.doesNotMatch(wizard, /STREAM_CHUNK_SIZE|STREAM_DELAY_MS/);
  assert.doesNotMatch(wizard, /Promise\.allSettled/);
  assert.doesNotMatch(wizard, /stopWorldviewGeneration/);
  assert.doesNotMatch(wizard, /stopProtagonistGeneration/);
  assert.doesNotMatch(wizard, /进入主角抽卡/);
  assert.doesNotMatch(wizard, /进入书名包装/);
  assert.doesNotMatch(wizard, /进入立项种子/);
  assert.doesNotMatch(wizard, /进入压力测试/);
  assert.doesNotMatch(wizard, /进入正典预览/);
  assert.doesNotMatch(wizard, /void loadWorldviewBatch\(sessionId\)/);
  assert.doesNotMatch(wizard, /void loadProtagonistBatch\(sessionId\)/);
  assert.doesNotMatch(wizard, /void loadTitlePackagingBatch\(sessionId\)/);
  assert.doesNotMatch(wizard, /void runCoreConstitutionLane\(\)/);
  assert.doesNotMatch(wizard, /reviewConstitution\.mutate\(sessionId\)/);
  assert.doesNotMatch(wizard, /previewCanon\.mutate\(sessionId\)/);
  assert.doesNotMatch(wizard, /loading=\{.*\}>下一步<\/Button>/);
  assert.doesNotMatch(wizard, />关闭<\/Button>/);
  assert.doesNotMatch(wizard, /关闭/);
  assert.doesNotMatch(wizard, /disabled=\{!selectedWorldview\}/);
  assert.doesNotMatch(wizard, /disabled=\{!selectedProtagonist\}/);
  assert.doesNotMatch(wizard, /disabled=\{!Object\.keys\(novelConstitution\)\.length\}/);
  assert.doesNotMatch(wizard, /loading=\{protagonistBatchLoading \|\| loadProtagonist\.isPending\} onClick=\{enterProtagonist\}>进入主角抽卡/);

  for (const field of [
    "one_sentence_pitch",
    "core_world_rule",
    "social_pressure",
    "power_or_resource_system",
    "conflict_engine_seed",
    "protagonist_entry",
    "long_form_potential",
    "key_entities",
    "rules_not_to_break",
    "reader_hooks",
    "selling_point",
    "writing_risk",
    "opening_situation",
    "world_rule_connection",
    "long_term_desire",
    "ability_cost",
    "relationship_hooks",
    "conflict_seed",
    "reader_satisfaction",
  ]) {
    assert.match(wizard, new RegExp(field));
  }
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

test("workspace drafts chapters through a resumable background job", () => {
  const workspace = read("src/pages/WorkspacePage.tsx");
  const studio = read("src/api/studio.ts");

  assert.match(studio, /async_mode:\s*true/);
  assert.match(studio, /draftChapter/);
  assert.match(studio, /getJob/);
  assert.match(workspace, /draftJobId/);
  assert.match(workspace, /draftJobQuery/);
  assert.match(workspace, /refetchInterval/);
  assert.match(workspace, /studioApi\.getJob\(draftJobId\)/);
  assert.match(workspace, /后台任务已创建/);
});

test("outline studio exposes long-novel planning controls", () => {
  const outline = read("src/pages/OutlineStudioPage.tsx");
  const outlineDirectory = read("src/pages/outline/OutlineDirectory.tsx");
  const outlineEditor = read("src/pages/outline/OutlineEditorPanel.tsx");
  const scalePlan = read("src/pages/outline/scalePlan.ts");
  const outlineUtils = read("src/pages/outline/outlineUtils.ts");
  const studio = read("src/api/studio.ts");
  const outlineBundle = [outline, outlineDirectory, outlineEditor, scalePlan, outlineUtils].join("\n");
  const mountedOutlineUi = [outline, outlineDirectory, outlineEditor].join("\n");

  for (const label of ["总纲", "卷纲", "章节", "章纲", "大纲正文"]) {
    assert.match(outlineBundle, new RegExp(label));
  }
  for (const deletedPath of [
    "src/pages/outline/OutlineGenerationModal.tsx",
    "src/pages/outline/OutlineInferenceGraph.tsx",
    "src/pages/outline/outlineGeneration.ts",
    "src/pages/outline/useOutlineGenerationJob.ts",
    "src/pages/outline/CanonStudioPanel.tsx",
  ]) {
    assert.equal(existsSync(new URL(`../${deletedPath}`, import.meta.url)), false, `${deletedPath} should stay deleted`);
  }
  assert.doesNotMatch(mountedOutlineUi, /生成大纲|批量生成章纲|openGenerationPreview|OutlineGenerationModal|outlinePreviewOpen|confirmApplyOutlineUpdate/);
  assert.doesNotMatch(outlineDirectory, /<Plus|title="添加"/);
  assert.match(outline, /useTopologyInference/);
  assert.doesNotMatch(outlineBundle, /生成卷纲/);
  assert.match(outlineBundle, /target_words/);
  assert.match(outlineBundle, /volume_count/);
  assert.match(outlineBundle, /chapters_per_volume/);
  assert.match(outlineBundle, /chapter_word_target/);
  assert.match(outlineBundle, /scale_plan/);
  assert.match(outlineBundle, /chapter_word_min/);
  assert.match(outlineBundle, /chapter_word_max/);
  assert.match(outline, /App\.useApp/);
  assert.doesNotMatch(outline, /Modal\.confirm/);
  assert.match(outline, /OutlineDirectory/);
  assert.match(outline, /OutlineEditorPanel/);
  assert.match(outline, /OutlineDebatePanel/);
  assert.doesNotMatch(outline, /CanonStudioPanel/);
  assert.match(outlineDirectory, /显示大纲正文/);
  assert.match(outlineDirectory, /隐藏大纲正文/);
  assert.match(outlineDirectory, /outline-directory-toolbar/);
  assert.match(outlineDirectory, /outline-directory-icon-button/);
  assert.match(outlineDirectory, /ListChecks/);
  assert.match(outlineDirectory, /EyeOff/);
  assert.match(outlineDirectory, /Eye/);
  assert.match(outlineDirectory, /setDetailOpen\(!detailOpen\)/);
  assert.match(outlineDirectory, /setBatchManagementEnabled\(!batchManagementEnabled\)/);
  assert.doesNotMatch(outlineDirectory, /outline-detail-toggle/);
  assert.doesNotMatch(outlineDirectory, /outline-batch-toggle/);
  assert.doesNotMatch(outlineDirectory, /<Switch/);
  assert.match(outlineEditor, /大纲正文/);
  assert.doesNotMatch(outlineEditor, /大纲工作台/);
  assert.ok(outline.split("\n").length < 430, "OutlineStudioPage should remain an orchestrator, not a monolith");
  assert.doesNotMatch(outline, /window\.setInterval/);
  assert.doesNotMatch(outline, /OUTLINE_AGENT_STEPS\.map/);
  assert.doesNotMatch(outlineBundle, /13Agent推演链/);
  assert.match(outline, /selectedChapterIds/);
  assert.match(outline, /sameStringArray/);
  assert.match(outlineDirectory, /批量管理/);
  assert.match(outlineDirectory, /batchManagementEnabled/);
  assert.match(outlineDirectory, /已选 \{selectedChapterIdsAcrossDirectory\.length\}章/);
  assert.match(outlineBundle, /删章节/);
  assert.match(outlineBundle, /删总纲/);
  assert.match(outlineBundle, /删除卷纲/);
  assert.match(outlineBundle, /删卷纲/);
  assert.match(outlineDirectory, /全选章节/);
  assert.match(outlineDirectory, /可删卷纲/);
  assert.doesNotMatch(outlineDirectory, /全选全部章节/);
  assert.doesNotMatch(outlineDirectory, /批量删除选中/);
  assert.doesNotMatch(outlineDirectory, /全选可删除卷纲/);
  assert.doesNotMatch(outlineDirectory, /批量删除卷纲/);
  assert.match(outline, /deleteSelectedChapters/);
  assert.match(outline, /deleteSelectedVolumes/);
  assert.match(outline, /confirmClearOutline/);
  assert.match(outline, /confirmDeleteVolume/);
  assert.match(outline, /confirmBatchDeleteVolumes/);
  assert.match(outline, /hasDeletableOutline/);
  assert.doesNotMatch(outline, /generateFromExistingOutline/);
  assert.doesNotMatch(outline, /请先生成总纲/);
  assert.match(outlineDirectory, /renderVolumeChapterTree/);
  assert.match(outlineDirectory, /outline-directory-bulk-actions/);
  assert.match(outlineDirectory, /outline-bulk-footer/);
  assert.match(outlineDirectory, /outline-directory-bulk-actions[\s\S]*删总纲/);
  assert.match(outlineDirectory, /selectedVolumeIds/);
  assert.match(outlineDirectory, /toggleAllVolumeOutlines/);
  assert.match(outlineDirectory, /outline-volume-group/);
  assert.match(outlineDirectory, /outline-nested-chapters/);
  assert.doesNotMatch(outlineDirectory, /outline-trash/);
  assert.doesNotMatch(outlineDirectory, /回收站/);
  assert.doesNotMatch(outline, /回收站/);
  assert.match(outline, /toggleDirectorySelection/);
  assert.doesNotMatch(outlineEditor, /generateFromExistingOutline/);
  assert.match(studio, /outline\/debate\/sessions/);
  assert.doesNotMatch(studio, /outline\/book\/generate/);
  assert.doesNotMatch(studio, /outline\/book\/commit/);
  assert.doesNotMatch(studio, /outline\/chapters\/batch-generate/);
  assert.doesNotMatch(studio, /outline\/chapters\/commit/);
  assert.doesNotMatch(outlineBundle, /bookOutlineGenerate|chapterOutlineBatchGenerate/);
  assert.doesNotMatch(outlineEditor, /删除总纲|删除大纲|删除卷纲|删除章纲/);
  assert.match(outlineEditor, /formatOutlineDocument/);
  assert.match(outlineEditor, /formatVolumeOutlineDocument/);
  assert.match(outlineEditor, /formatChapterOutlineDocument/);
  assert.match(outlineEditor, /outline-prose/);
  assert.doesNotMatch(outlineEditor, /readableJson/);
  assert.doesNotMatch(outlineEditor, /Descriptions/);
  assert.match(outline, /setLastOutlinePlan/);
  assert.doesNotMatch(outlineBundle, /正典补全|长篇小说多 Agent 协作推演与正典补全系统/);
  assert.match(studio, /deleteVolume/);
  assert.match(studio, /\/volumes\/\$\{volumeId\}/);
  assert.match(studio, /chapters\/trash\/batch/);
  assert.doesNotMatch(outline, /outline-generate-actions/);
  assert.doesNotMatch(outline, />\\s*起始章节\\s*</);
  assert.doesNotMatch(outline, />\\s*本次生成章纲数\\s*</);
  assert.doesNotMatch(outline, /setOutlinePreviewOpen\\(false\\);\\s*setSelectedView/);
  assert.match(studio, /outline_plan/);
});

test("outline studio removes the legacy generation modal flow", () => {
  const outline = read("src/pages/OutlineStudioPage.tsx");
  const outlineUtils = read("src/pages/outline/outlineUtils.ts");

  assert.match(outlineUtils, /sameStringArray/);
  assert.doesNotMatch(outlineUtils, /RunningInferenceOptions|BOOK_OUTLINE_SWARM_AGENT_ROLES|CHAPTER_OUTLINE_AGENT_ROLES/);
  assert.doesNotMatch(outline, /buildRunningInferenceSteps\(\{\s*generationMode/);
  assert.doesNotMatch(outline, /useTopologyInference: Boolean\(values\.use_topology_inference\)/);
  assert.doesNotMatch(outline, /useOutlineGenerationJob/);
  for (const deletedPath of [
    "src/pages/outline/OutlineGenerationModal.tsx",
    "src/pages/outline/OutlineInferenceGraph.tsx",
    "src/pages/outline/outlineGeneration.ts",
    "src/pages/outline/useOutlineGenerationJob.ts",
  ]) {
    assert.equal(existsSync(new URL(`../${deletedPath}`, import.meta.url)), false, `${deletedPath} should stay deleted`);
  }
});

test("outline studio exposes streaming debate engine phases", () => {
  const outline = read("src/pages/OutlineStudioPage.tsx");
  const panel = read("src/pages/outline/OutlineDebatePanel.tsx");
  const studio = read("src/api/studio.ts");
  const styles = read("src/styles/index.css");

  assert.match(outline, /OutlineDebatePanel/);
  assert.match(studio, /outline\/debate\/sessions/);
  assert.match(studio, /streamOutlineDebatePhase/);
  assert.match(studio, /type: "delta"/);
  assert.match(studio, /display_text\?: string/);
  assert.match(studio, /handoff\?:/);
  assert.match(studio, /confirmOutlineDebatePhase/);
  assert.match(studio, /commitOutlineDebateCandidates/);
  assert.match(studio, /outline\/debate\/sessions\/\$\{sessionId\}\/commit/);
  assert.match(studio, /candidate_status/);
  assert.match(studio, /confirmation_items/);
  assert.match(studio, /target_volume_no/);
  assert.match(studio, /target_chapter_no/);
  assert.match(studio, /item_key/);
  assert.match(studio, /confirmed_candidates/);
  assert.match(studio, /formal_commit/);
  assert.match(panel, /讨论总纲/);
  assert.match(panel, /讨论卷纲/);
  assert.match(panel, /讨论章纲/);
  assert.match(panel, /streamOutlineDebatePhase/);
  assert.match(panel, /appendTurnDelta/);
  assert.match(panel, /emptyStreamingTurn/);
  assert.match(panel, /event\.type === "delta"/);
  assert.match(panel, /display_text !== undefined/);
  assert.match(panel, /event\.turn\.handoff\?\.display/);
  assert.match(panel, /交接：\{event\.turn\.handoff\.display\}/);
  assert.match(panel, /真实 Agent 议事流/);
  assert.doesNotMatch(panel, /真实 Agent 议事流会逐条显示/);
  assert.doesNotMatch(panel, /outline-debate-intro/);
  assert.doesNotMatch(panel, /Scale Planner：/);
  assert.doesNotMatch(outline, /Scale Planner：\$\{debateScalePlan/);
  assert.match(studio, /canon_materializations/);
  assert.match(panel, /Mentions/);
  assert.match(panel, /加入讨论/);
  assert.match(panel, /发表意见/);
  assert.match(panel, /继续下一轮/);
  assert.match(panel, /打断发言/);
  assert.match(panel, /形成阶段结论/);
  assert.match(panel, /确认总纲/);
  assert.match(panel, /确认本卷/);
  assert.match(panel, /确认本章/);
  assert.match(panel, /activeItemKey/);
  assert.match(panel, /confirmation_items/);
  assert.match(panel, /target_volume_no/);
  assert.match(panel, /target_chapter_no/);
  assert.match(panel, /item_key/);
  assert.match(panel, /写入正式大纲/);
  assert.match(panel, /待确认|已确认|已过期/);
  assert.match(panel, /candidateStatusLabel/);
  assert.match(panel, /confirmActivePhase/);
  assert.match(panel, /commitConfirmedCandidates/);
  assert.match(panel, /allCandidatesConfirmed/);
  assert.doesNotMatch(panel, /议事正文/);
  assert.doesNotMatch(panel, /隐藏正文/);
  assert.doesNotMatch(panel, /显示正文/);
  assert.doesNotMatch(panel, /bodyHidden/);
  assert.match(panel, /outline-debate-event-text/);
  assert.doesNotMatch(panel, /outline-debate-requirement/);
  assert.doesNotMatch(panel, /is-body-hidden/);
  assert.match(panel, /outline-debate-composer-dock/);
  assert.match(panel, /streamViewportRef/);
  assert.match(panel, /streamEndRef/);
  assert.match(panel, /回到最新发言/);
  assert.match(panel, /scrollIntoView/);
  assert.match(panel, /outline-debate-round-separator/);
  assert.match(panel, /is-active-speaker/);
  assert.match(panel, /当前发言/);
  assert.match(panel, /joinDiscussion \? \(/);
  assert.doesNotMatch(panel, /快速本地推演/);
  assert.doesNotMatch(panel, /local_preview/);
  assert.doesNotMatch(panel, /阶段候选产物/);
  assert.doesNotMatch(panel, /outline-debate-artifacts/);
  assert.doesNotMatch(panel, /artifactsCollapsed/);
  assert.doesNotMatch(panel, /展开候选|收起候选/);
  assert.doesNotMatch(panel, /outline-debate-artifact-summary/);
  assert.doesNotMatch(panel, /Agent 能力/);
  assert.doesNotMatch(panel, /阶段校验/);
  assert.doesNotMatch(panel, /renderAgentSpecs/);
  assert.doesNotMatch(panel, /renderValidationReport/);
  assert.match(studio, /OutlineDebateAgentSpec/);
  assert.match(studio, /OutlineDebateValidationReport/);
  assert.match(studio, /postOutlineDebateMessage/);
  assert.match(studio, /interruptOutlineDebateSession/);
  assert.match(studio, /join_discussion/);
  assert.doesNotMatch(studio, /local_preview/);
  assert.match(studio, /event: "pause"|type: "pause"/);
  assert.match(styles, /outline-debate-panel/);
  assert.match(styles, /outline-debate-composer/);
  assert.match(styles, /outline-directory-toolbar/);
  assert.match(styles, /outline-directory-icon-button/);
  assert.doesNotMatch(styles, /outline-batch-toggle/);
  assert.doesNotMatch(styles, /outline-detail-toggle/);
  assert.match(styles, /grid-template-columns:\s*minmax\(210px,\s*250px\)\s*minmax\(0,\s*1fr\)/);
  assert.match(styles, /white-space:\s*pre-wrap/);
  assert.match(styles, /overflow-wrap:\s*anywhere/);
  assert.doesNotMatch(styles, /outline-debate-panel\.is-body-hidden/);
  assert.doesNotMatch(styles, /outline-debate-requirement/);
  assert.match(styles, /\.outline-debate-panel\s*\{[\s\S]*overflow-y:\s*auto/);
  assert.match(styles, /\.outline-debate-panel\s*\{[\s\S]*scrollbar-gutter:\s*stable/);
  assert.match(styles, /\.outline-debate-panel\s*\{[\s\S]*overscroll-behavior:\s*contain/);
  assert.match(styles, /\.outline-debate-body\s*\{[\s\S]*grid-template-columns:\s*minmax\(0,\s*1fr\)/);
  assert.match(styles, /\.outline-debate-body\s*\{[\s\S]*min-height:\s*clamp\(420px,\s*58vh,\s*760px\)/);
  assert.match(styles, /\.outline-debate-composer-dock\s*\{(?:(?!\}).)*display:\s*grid/s);
  assert.doesNotMatch(styles, /\.outline-debate-composer-dock\s*\{(?:(?!\}).)*position:\s*sticky/s);
  assert.doesNotMatch(styles, /\.outline-debate-composer-dock\s*\{(?:(?!\}).)*bottom:\s*0/s);
  assert.doesNotMatch(styles, /\.outline-debate-composer-dock\s*\{(?:(?!\}).)*linear-gradient/s);
  assert.match(styles, /outline-debate-stream-body[\s\S]*overflow-y:\s*auto/);
  assert.doesNotMatch(styles, /outline-debate-body\.is-artifacts-collapsed/);
  assert.doesNotMatch(styles, /outline-debate-artifacts/);
  assert.match(styles, /outline-debate-round-separator/);
  assert.match(styles, /outline-debate-event\.is-active-speaker/);
});

test("world generation previews candidates before users commit them", () => {
  const world = read("src/pages/WorldPage.tsx");
  const studio = read("src/api/studio.ts");

  assert.match(studio, /preview_only\?: boolean/);
  assert.match(world, /preview_only: true/);
  assert.match(world, /pendingGeneratedSettings/);
  assert.match(world, /候选设定审批/);
  assert.match(world, /确认写入/);
  assert.match(world, /丢弃候选/);
  assert.match(world, /commitGeneratedSettings/);
  assert.match(world, /createWorldFact/);
  assert.match(world, /createEntity/);
  assert.doesNotMatch(world, /Agent 已生成 \$\{total\} 条候选设定`;\s*setGenerateTarget/);
});

test("settings subsections group file tree, characters, world, graph, and foreshadowing under one UI", () => {
  const settingsNav = read("src/components/SettingsSectionNav.tsx");
  const styles = read("src/styles/index.css");
  const settingsTree = read("src/pages/SettingsWorkbenchPage.tsx");
  const profile = read("src/pages/ProjectProfilePage.tsx");
  const characters = read("src/pages/CharactersPage.tsx");
  const world = read("src/pages/WorldPage.tsx");
  const graph = read("src/pages/GraphPage.tsx");
  const foreshadowing = read("src/pages/ForeshadowingPage.tsx");

  for (const section of ["tree", "profile", "characters", "world", "graph", "foreshadowing"]) {
    assert.match(settingsNav, new RegExp(`settings/\\$\\{section.key\\}|settings/${section}`));
  }
  assert.match(settingsNav, /设定文件树/);
  assert.match(settingsTree, /SettingsSectionNav active="tree"/);
  assert.match(settingsTree, /getSettingsTree/);
  assert.match(settingsTree, /listCanonVersions/);
  assert.match(settingsTree, /getCanonVersionTimeline/);
  assert.match(settingsTree, /rollbackCanonVersion/);
  assert.match(settingsTree, /approveCanonProposal/);
  assert.match(settingsTree, /archiveCanonItems/);
  assert.match(settingsTree, /createCanonFolder/);
  assert.match(settingsTree, /moveCanonNode/);
  assert.match(settingsTree, /setCanonLocks/);
  assert.match(settingsTree, /getCanonImpact/);
  assert.match(settingsTree, /scanCanonDuplicates/);
  assert.match(settingsTree, /exportCanonPackage/);
  assert.match(settingsTree, /影响索引/);
  assert.match(settingsTree, /版本/);
  assert.match(settingsTree, /候选/);
  for (const label of ["小说宪法", "核心矛盾系统", "关系图谱", "候选变更", "来源", "关系", "章节轴", "Agent 审计", "重复项", "差异对比", "冻结字段", "人物卡当前状态", "正典健康度仪表盘", "新建文件夹", "导出 Markdown", "导出 JSON", "扫描重复项"]) {
    assert.match(settingsTree, new RegExp(label));
  }
  assert.match(settingsNav, /作品资料/);
  assert.match(profile, /SettingsSectionNav active="profile"/);
  assert.match(profile, /作品资料与故事圣经/);
  assert.match(profile, /getCreationProfile/);
  assert.match(profile, /创作 Star 立项档案/);
  assert.match(profile, /世界观抽卡/);
  assert.match(profile, /主角人设抽卡/);
  assert.match(profile, /书名与包装/);
  assert.match(profile, /核心矛盾系统/);
  assert.match(profile, /小说宪法/);
  assert.match(profile, /压力测试/);
  assert.match(profile, /profile-creation-archive/);
  assert.match(profile, /formatProfileValue/);
  assert.match(characters, /SettingsSectionNav active="characters"/);
  assert.match(world, /SettingsSectionNav active="world"/);
  assert.match(graph, /SettingsSectionNav active="graph"/);
  assert.match(foreshadowing, /SettingsSectionNav active="foreshadowing"/);
  assert.match(foreshadowing, /settings-canon-card/);
  assert.match(graph, /settings-stat-card/);
  assert.match(styles, /grid-template-columns: 34px minmax\(0, 1fr\)/);
  assert.match(styles, /settings-tree-card/);
  assert.match(styles, /settings-impact-panel/);
  assert.match(styles, /settings-character-card/);
  assert.match(styles, /settings-version-diff/);
  assert.match(styles, /min-height: 118px/);
  assert.match(styles, /-webkit-line-clamp: 2/);
});

test("outline studio hides inline canon completion panel content", () => {
  const outline = read("src/pages/OutlineStudioPage.tsx");
  const studio = read("src/api/studio.ts");

  assert.doesNotMatch(outline, /CanonStudioPanel/);
  assert.equal(existsSync(new URL("../src/pages/outline/CanonStudioPanel.tsx", import.meta.url)), false);
  assert.doesNotMatch(studio, /runCanonStudio/);
  assert.doesNotMatch(studio, /getCanonStore/);
  assert.doesNotMatch(studio, /getCanonFinalOutline/);
  assert.doesNotMatch(studio, /canon-studio\//);
});

test("docs describe the split API and outline frontend structure", () => {
  const readme = readRoot("README.md");
  const agents = readRoot("AGENTS.md");

  for (const doc of [readme, agents]) {
    assert.match(doc, /backend\/app\/api\/v1\/endpoints\/project_studio\.py/);
    assert.match(doc, /backend\/app\/api\/v1\/endpoints\/knowledge\.py/);
    assert.match(doc, /backend\/app\/api\/v1\/endpoints\/writing\.py/);
    assert.match(doc, /frontend\/src\/pages\/outline\//);
    assert.match(doc, /OutlineStudioPage/);
    assert.doesNotMatch(doc, /canon-studio|final_outline|canon_store|正典补全/);
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
  assert.match(batch, /useQuery/);
  assert.match(batch, /listChapters/);
  assert.match(batch, /getJob/);
  assert.match(batch, /localStorage/);
  assert.match(batch, /latestRecentJob/);
  assert.match(batch, /saveJobId\(projectId,\s*latestRecentJob\.id\)/);
  assert.match(batch, /请先确认章纲/);
  assert.match(batch, /批量任务已创建/);
  assert.match(batch, /已完成章节/);
  assert.match(batch, /失败章节/);
  assert.match(batch, /暂停/);
  assert.match(batch, /恢复/);
  assert.match(batch, /取消/);
  assert.match(batch, /重试/);
  assert.doesNotMatch(batch, /initialValues=\{\{ chapter_start: 1, chapter_end: 3 \}\}/);
  assert.doesNotMatch(batch, /正在生成章节\.\.\./);
  assert.doesNotMatch(batch, /mutation\.isPending \? 45/);
  assert.match(studio, /\/jobs\/\$\{jobId\}/);
  assert.match(studio, /\/write\/pause/);
  assert.match(studio, /\/write\/resume/);
  assert.match(studio, /\/write\/cancel/);
  assert.match(studio, /\/jobs\/\$\{jobId\}\/retry/);
});

test("job page renders readable outline debate agent run details", () => {
  const job = read("src/pages/JobPage.tsx");

  for (const label of ["LLM 来源", "本地降级", "议事轨迹", "回合数", "原始载荷"]) {
    assert.match(job, new RegExp(label));
  }
  assert.match(job, /isOutlineDebateRun/);
  assert.match(job, /renderAgentRunDetails/);
  assert.match(job, /trace_events/);
  assert.match(job, /outline_debate/);
  assert.doesNotMatch(job, /outline_swarm|Swarm Trace|迭代次数/);
  assert.doesNotMatch(job, /JSON\.stringify\(run\.output_payload, null, 2\)\.slice\(0, 500\)/);
});

test("Ant Design application context wraps pages that use App.useApp", () => {
  const app = read("src/App.tsx");

  assert.match(app, /App as AntdApp/);
  assert.match(app, /<AntdApp>/);
});
