import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");

test("agents page supports prompt workflow nodes, runtime status, and restoring default prompts", () => {
  const page = read("src/pages/AgentsPage.tsx");
  const studio = read("src/api/studio.ts");
  const types = read("src/types/api.ts");

  assert.match(types, /"agent" \| "control" \| "prompt"/);
  assert.match(types, /runtime_status/);
  assert.match(types, /entrypoints/);
  assert.match(studio, /restoreAgentPrompt/);
  assert.match(studio, /prompt\/restore/);
  assert.match(page, /恢复默认/);
  assert.match(page, /restorePrompt/);
  assert.match(page, /runtime_status/);
  assert.match(page, /selectedAgent/);
  assert.doesNotMatch(page, /selectedNode\?\.type === "agent" \? \(/);
});

test("agents page labels prompt nodes by subtype and exposes node schemas", () => {
  const page = read("src/pages/AgentsPage.tsx");
  const types = read("src/types/api.ts");

  assert.match(types, /node_subtype\?: string/);
  assert.match(types, /input_schema\?: WorkflowNodeSchema/);
  assert.match(types, /output_schema\?: WorkflowNodeSchema/);
  assert.match(page, /nodeSubtypeLabel/);
  assert.match(page, /prompt_agent/);
  assert.match(page, /输入 Schema/);
  assert.match(page, /输出 Schema/);
});

test("agents page lets each workflow agent select an LLM model", () => {
  const page = read("src/pages/AgentsPage.tsx");
  const studio = read("src/api/studio.ts");
  const types = read("src/types/api.ts");

  assert.match(types, /LLMModelOption/);
  assert.match(types, /model_configs/);
  assert.match(types, /model_config_id/);
  assert.match(studio, /listLlmModels/);
  assert.match(studio, /updateAgentModelConfig/);
  assert.match(studio, /deleteAgentModelConfig/);
  assert.match(studio, /\/llm\/models/);
  assert.match(studio, /\/agent-model-configs/);
  assert.match(page, /模型选择/);
  assert.match(page, /模型厂商/);
  assert.match(page, /模型版本/);
  assert.match(page, /selectedProvider/);
  assert.match(page, /selectedModel/);
  assert.match(page, /selectedModelConfigAgentName/);
  assert.match(page, /canConfigureSelectedModel/);
  assert.match(page, /providerOptions/);
  assert.match(page, /filteredModelOptions/);
  assert.match(page, /gridTemplateColumns: "minmax\(0, 1fr\) minmax\(0, 1fr\)"/);
  assert.match(page, /optionLabelProp="title"/);
  assert.match(page, /optionFilterProp="title"/);
  assert.match(page, /popupMatchSelectWidth=\{false\}/);
  assert.match(page, /whiteSpace: "normal"/);
  assert.match(page, /saveModelConfig/);
  assert.match(page, /restoreModelConfig/);
  assert.match(page, /listLlmModels/);
  assert.match(page, /agent_name: selectedModelConfigAgentName/);
});

test("agents page defaults to lifecycle workflows and keeps prompt library visible", () => {
  const page = read("src/pages/AgentsPage.tsx");
  const types = read("src/types/api.ts");

  assert.match(types, /workflow_kind\?: "runtime" \| "prompt_lifecycle" \| "prompt_library" \| string/);
  assert.match(types, /trigger_policy\?: string/);
  assert.match(types, /tags\?: string\[\]/);
  assert.match(types, /configurable\?: boolean/);
  assert.match(types, /node_runtime_status\?:/);
  assert.match(page, /executableWorkflows/);
  assert.match(page, /referenceWorkflows/);
  assert.match(page, /showReferenceWorkflows/);
  assert.match(page, /onlyRealRuntimeNodes/);
  assert.match(page, /outline_debate_engine/);
  assert.doesNotMatch(page, /useState\("chapter_closed_loop_lifecycle"\)/);
  assert.match(page, /workflowKindLabel/);
  assert.match(page, /prompt_lifecycle/);
  assert.match(page, /prompt_library/);
  assert.match(page, /运行工作流/);
  assert.match(page, /提示词参考/);
});

test("agents page separates configurable agents from readonly runtime nodes", () => {
  const page = read("src/pages/AgentsPage.tsx");

  assert.match(page, /configurableAgentForNode/);
  assert.match(page, /canConfigureSelectedAgent/);
  assert.match(page, /canEditControlDescription/);
  assert.match(page, /nodeOperationalLabel/);
  assert.match(page, /内部运行 Agent/);
  assert.match(page, /Prompt 任务/);
  assert.match(page, /运行名/);
  assert.match(page, /只读运行节点/);
  assert.doesNotMatch(page, /activeWorkflow\.nodes\.map/);
});

test("agents page exposes Deep Agent and LangSmith management controls", () => {
  const page = read("src/pages/AgentsPage.tsx");
  const studio = read("src/api/studio.ts");
  const types = read("src/types/api.ts");

  assert.match(types, /DeepAgentConfig/);
  assert.match(types, /DeepAgentSession/);
  assert.match(types, /DeepAgentToolCall/);
  assert.match(types, /LangSmithStatus/);
  assert.match(studio, /getDeepAgentConfig/);
  assert.match(studio, /updateDeepAgentConfig/);
  assert.match(studio, /createDeepAgentSession/);
  assert.match(studio, /listDeepAgentSessions/);
  assert.match(studio, /approveDeepAgentToolCall/);
  assert.match(studio, /rejectDeepAgentToolCall/);
  assert.match(studio, /getLangSmithStatus/);
  assert.match(studio, /runLangSmithEval/);
  assert.match(studio, /\/deep-agent\/config/);
  assert.match(studio, /\/langsmith\/status/);
  assert.match(page, /Deep Agent 管理/);
  assert.match(page, /LangSmith 管理/);
  assert.match(page, /隐私模式/);
  assert.match(page, /待审批工具/);
  assert.match(page, /createDeepAgentSession/);
  assert.match(page, /runLangSmithEval/);
});
