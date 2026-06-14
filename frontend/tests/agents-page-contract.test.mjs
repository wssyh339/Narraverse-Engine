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
});
