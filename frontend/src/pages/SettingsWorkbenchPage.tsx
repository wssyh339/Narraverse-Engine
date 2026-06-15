import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Badge, Button, Card, Col, Descriptions, Empty, Input, List, Modal, Progress, Row, Space, Statistic, Tabs, Tag, Tooltip, Tree, Typography, message } from "antd";
import type { DataNode } from "antd/es/tree";
import { Archive, Check, Clock3, Download, FolderPlus, GitCompare, GitMerge, History, ListTree, Lock, Network, RotateCcw, Search, ShieldCheck, X } from "lucide-react";
import type { Key } from "react";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { studioApi } from "../api/studio";
import { SettingsSectionNav } from "../components/SettingsSectionNav";
import type { CanonChangeProposal, CanonImpact, CanonNode, CanonRefType, CanonVersion } from "../types/api";

const refTypeLabels: Record<string, string> = {
  character: "人物",
  entity: "实体",
  world_fact: "世界观",
  foreshadowing: "伏笔",
  folder: "目录",
};

const fieldLabels: Record<string, string> = {
  name: "名称",
  title: "标题",
  role_type: "角色类型",
  entity_type: "实体类型",
  category: "分类",
  importance_level: "重要度",
  importance_score: "重要分",
  current_status: "状态",
  payoff_status: "回收状态",
  summary: "摘要",
  description: "描述",
  content: "内容",
  confidence: "置信度",
  source_chapter_id: "来源章节",
  first_appearance_chapter_id: "首次出现",
  last_seen_chapter_id: "最近出现",
  updated_reason: "更新原因",
  change_reason: "变更原因",
  source: "来源",
  source_agent: "来源 Agent",
  source_job_id: "来源任务",
  related_entity_ids: "相关实体",
  related_character_ids: "相关人物",
  goals: "目标",
  motivations: "动机",
  secrets: "秘密",
  abilities: "能力",
  weaknesses: "伤口/弱点",
  character_arc: "人物弧光",
};

const STATIC_FOLDERS: Array<[string, string | null, string, number, string]> = [
  ["folder:root", null, "正典设定集", 0, "全项目正典的统一入口。"],
  ["folder:project", "folder:root", "作品资料", 10, "故事圣经、小说宪法和核心矛盾系统。"],
  ["folder:project:story-bible", "folder:project", "故事圣经", 11, "作品基础设定和叙事约束。"],
  ["folder:project:constitution", "folder:project", "小说宪法", 12, "不可轻易改写的创作公约。"],
  ["folder:project:core-conflict", "folder:project", "核心矛盾系统", 13, "主线冲突、不可逆选择和代价结构。"],
  ["folder:characters", "folder:root", "人物", 20, "按重要度、活跃状态和候选状态管理角色卡。"],
  ["folder:characters:core", "folder:characters", "核心角色", 21, "主角、关键对手和长期驱动主线的人物。"],
  ["folder:characters:major", "folder:characters", "主要角色", 22, "高频出场并影响卷章推进的人物。"],
  ["folder:characters:supporting", "folder:characters", "配角", 23, "局部场景、线索或关系功能人物。"],
  ["folder:characters:faction", "folder:characters", "阵营角色", 24, "按势力、组织或阵营归属管理的人物。"],
  ["folder:characters:inactive", "folder:characters", "已退场 / 失踪 / 死亡", 25, "暂离主线或不可继续活跃的人物。"],
  ["folder:characters:candidate", "folder:characters", "待确认候选", 26, "Agent 生成但尚未正式入库的人物候选。"],
  ["folder:world", "folder:root", "世界", 30, "世界规则、历史、地理、文化、禁忌和时间线。"],
  ["folder:world:rules", "folder:world", "规则", 31, "硬规则、软规则、能力边界和制度约束。"],
  ["folder:world:history", "folder:world", "历史", 32, "前史、重大事件和长期因果。"],
  ["folder:world:geography", "folder:world", "地理", 33, "地点、区域、交通和空间压力。"],
  ["folder:world:culture", "folder:world", "文化", 34, "风俗、语言、阶层、宗教与价值观。"],
  ["folder:world:taboo", "folder:world", "禁忌", 35, "不能触碰的规则、秘密和社会边界。"],
  ["folder:world:timeline", "folder:world", "时间线", 36, "按章节和故事内时间追踪设定公开程度。"],
  ["folder:entities", "folder:root", "实体", 40, "地点、组织、物件、线索和事件。"],
  ["folder:entities:locations", "folder:entities", "地点", 41, "空间、场景和据点。"],
  ["folder:entities:organizations", "folder:entities", "组织", 42, "势力、机构、门派和公司。"],
  ["folder:entities:items", "folder:entities", "物件", 43, "道具、武器、信物和资源。"],
  ["folder:entities:clues", "folder:entities", "线索", 44, "谜题碎片、证据和未解释信息。"],
  ["folder:entities:events", "folder:entities", "事件", 45, "已经发生或计划发生的剧情事件。"],
  ["folder:graph", "folder:root", "关系图谱", 50, "人物、势力、线索和冲突关系的索引入口。"],
  ["folder:graph:characters", "folder:graph", "人物关系", 51, "人物间的情感、利益、敌友和秘密关系。"],
  ["folder:graph:factions", "folder:graph", "势力关系", 52, "组织、阵营和资源冲突关系。"],
  ["folder:graph:clues", "folder:graph", "线索关系", 53, "线索、秘密和事件的因果连接。"],
  ["folder:graph:conflicts", "folder:graph", "冲突关系", 54, "主线、卷线和场景冲突之间的依赖。"],
  ["folder:foreshadowing", "folder:root", "伏笔", 60, "伏笔从候选、预埋、提醒到回收的生命周期。"],
  ["folder:foreshadowing:candidate", "folder:foreshadowing", "待预埋", 61, "尚未正式植入章节的伏笔候选。"],
  ["folder:foreshadowing:planted", "folder:foreshadowing", "已预埋", 62, "已经在正文中出现的伏笔。"],
  ["folder:foreshadowing:reminded", "folder:foreshadowing", "待回收", 63, "已预埋但需要后续回收的伏笔。"],
  ["folder:foreshadowing:paid", "folder:foreshadowing", "已回收", 64, "已经完成 payoff 的伏笔。"],
  ["folder:foreshadowing:risky", "folder:foreshadowing", "风险伏笔", 65, "长期未回收、低置信度或状态异常的伏笔。"],
  ["folder:proposals", "folder:root", "候选变更", 70, "所有 Agent 生成、章后提取和冲突待处理的候选池。"],
  ["folder:proposals:agent", "folder:proposals", "Agent 生成候选", 71, "由工作流或工具主动生成的候选变更。"],
  ["folder:proposals:chapter", "folder:proposals", "章节后自动提取", 72, "正文生成后提取出的设定候选。"],
  ["folder:proposals:conflict", "folder:proposals", "冲突待处理", 73, "需要人工裁决或连续性检查的设定冲突。"],
];

const DIFF_IGNORED_KEYS = new Set(["id", "project_id", "created_at", "updated_at"]);
const LOCKABLE_FIELDS = ["summary", "secrets", "goals", "motivations", "abilities", "character_arc", "content", "description", "planned_payoff"];

interface DiffRow {
  field: string;
  before: string;
  after: string;
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "未填写";
  if (Array.isArray(value)) return value.length ? value.map(formatValue).join("、") : "未填写";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function normalizeText(value: unknown): string {
  return formatValue(value).replace(/\s+/g, " ").trim();
}

function proposalTitle(proposal: CanonChangeProposal): string {
  const after = proposal.after ?? {};
  return formatValue(after.name ?? after.title ?? after.content ?? "未命名候选");
}

function versionTitle(version: CanonVersion): string {
  return formatValue(version.content.name ?? version.content.title ?? version.content.content ?? `版本 ${version.version_no}`);
}

function downloadTextFile(filename: string, content: string, mime = "text/plain;charset=utf-8") {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function lower(value: unknown): string {
  return String(value ?? "").toLowerCase();
}

function containsAny(value: string, keys: string[]): boolean {
  return keys.some((key) => value.includes(key.toLowerCase()));
}

function virtualFolder(id: string, parentId: string | null, title: string, sortOrder: number, description: string): CanonNode {
  return {
    id,
    project_id: "",
    parent_id: parentId,
    node_type: "folder",
    ref_type: "folder",
    ref_id: id,
    title,
    sort_order: sortOrder,
    status: "active",
    importance_level: "medium",
    activity_status: "active",
    metadata: { virtual: true, description },
    content: null,
    created_at: null,
    updated_at: null,
  };
}

function proposalParent(proposal: CanonChangeProposal): string {
  const reason = lower(proposal.reason);
  if (proposal.operation === "merge" || containsAny(reason, ["冲突", "矛盾", "重复"])) return "folder:proposals:conflict";
  if (proposal.source_chapter_id || containsAny(reason, ["章节", "章后", "正文"])) return "folder:proposals:chapter";
  return "folder:proposals:agent";
}

function characterParent(node: CanonNode): string {
  const content = node.content ?? {};
  const status = lower(content.current_status ?? node.activity_status ?? node.status);
  const roleType = lower(content.role_type);
  if (containsAny(status, ["candidate", "候选", "待确认"])) return "folder:characters:candidate";
  if (containsAny(status, ["dead", "missing", "retired", "死亡", "失踪", "退场", "退休"])) return "folder:characters:inactive";
  if (containsAny(roleType, ["faction", "阵营", "势力", "组织"])) return "folder:characters:faction";
  if (node.importance_level === "core" || content.importance_level === "core") return "folder:characters:core";
  if (node.importance_level === "major" || content.importance_level === "major") return "folder:characters:major";
  return "folder:characters:supporting";
}

function worldParent(node: CanonNode): string {
  const category = lower(node.content?.category ?? node.title);
  if (containsAny(category, ["history", "历史", "前史"])) return "folder:world:history";
  if (containsAny(category, ["geo", "location", "地理", "地点", "区域", "空间"])) return "folder:world:geography";
  if (containsAny(category, ["culture", "文化", "宗教", "阶层", "风俗"])) return "folder:world:culture";
  if (containsAny(category, ["taboo", "禁忌", "禁止"])) return "folder:world:taboo";
  if (containsAny(category, ["timeline", "时间", "年表"])) return "folder:world:timeline";
  return "folder:world:rules";
}

function entityParent(node: CanonNode): string {
  const entityType = lower(node.content?.entity_type ?? node.title);
  if (containsAny(entityType, ["location", "place", "地点", "地理", "场景", "城市", "区域"])) return "folder:entities:locations";
  if (containsAny(entityType, ["organization", "faction", "组织", "势力", "机构", "门派", "公司"])) return "folder:entities:organizations";
  if (containsAny(entityType, ["item", "object", "artifact", "物件", "道具", "武器", "资源"])) return "folder:entities:items";
  if (containsAny(entityType, ["clue", "线索", "证据", "秘密"])) return "folder:entities:clues";
  if (containsAny(entityType, ["event", "事件", "战役", "事故"])) return "folder:entities:events";
  return "folder:entities:items";
}

function foreshadowingParent(node: CanonNode): string {
  const content = node.content ?? {};
  const payoffStatus = lower(content.payoff_status ?? node.activity_status);
  const confidence = Number(content.confidence ?? 1);
  if (payoffStatus === "paid_off" || containsAny(payoffStatus, ["已回收", "paid"])) return "folder:foreshadowing:paid";
  if (payoffStatus === "planted" || containsAny(payoffStatus, ["已预埋", "planted"])) return "folder:foreshadowing:planted";
  if (payoffStatus === "planned" || payoffStatus === "reminded" || containsAny(payoffStatus, ["待回收", "提醒"])) return "folder:foreshadowing:reminded";
  if (payoffStatus === "abandoned" || confidence < 0.55 || containsAny(payoffStatus, ["风险", "risky", "废弃"])) return "folder:foreshadowing:risky";
  return "folder:foreshadowing:candidate";
}

function parentForCanonNode(node: CanonNode): string {
  const customParent = node.metadata?.custom_folder_id ?? node.metadata?.display_parent_id;
  if (typeof customParent === "string" && customParent) return customParent;
  if (node.ref_type === "character") return characterParent(node);
  if (node.ref_type === "world_fact") return worldParent(node);
  if (node.ref_type === "entity") return entityParent(node);
  if (node.ref_type === "foreshadowing") return foreshadowingParent(node);
  return "folder:root";
}

function buildDisplayNodes(nodes: CanonNode[], proposals: CanonChangeProposal[]): CanonNode[] {
  const folders = STATIC_FOLDERS.map(([id, parentId, title, sortOrder, description]) => virtualFolder(id, parentId, title, sortOrder, description));
  const customFolders = nodes
    .filter((node) => node.node_type === "folder" && node.metadata?.custom_folder)
    .map((node) => ({ ...node, parent_id: typeof node.metadata?.display_parent_id === "string" ? node.metadata.display_parent_id : node.parent_id ?? "folder:root" }));
  const items = nodes
    .filter((node) => node.node_type === "item" && node.ref_type !== "folder")
    .map((node, index) => ({ ...node, parent_id: parentForCanonNode(node), sort_order: 100 + index }));
  const proposalItems = proposals.map((proposal, index) => ({
    id: `proposal:${proposal.id}`,
    project_id: proposal.project_id,
    parent_id: proposalParent(proposal),
    node_type: "item" as const,
    ref_type: "folder" as CanonRefType,
    ref_id: proposal.id,
    title: proposalTitle(proposal),
    sort_order: 200 + index,
    status: proposal.approval_status,
    importance_level: "medium",
    activity_status: "candidate",
    metadata: { virtual_proposal: true, proposal },
    content: {
      ...proposal.after,
      operation: proposal.operation,
      reason: proposal.reason,
      approval_status: proposal.approval_status,
      confidence: proposal.confidence,
      source_agent: proposal.source_agent,
      source_chapter_id: proposal.source_chapter_id,
      source_job_id: proposal.source_job_id,
      before: proposal.before,
    },
    created_at: proposal.created_at,
    updated_at: proposal.decided_at,
  }));
  return [...folders, ...customFolders, ...items, ...proposalItems];
}

function buildTreeData(nodes: CanonNode[]): DataNode[] {
  const byParent = new Map<string | null, CanonNode[]>();
  nodes.forEach((node) => {
    const key = node.parent_id ?? null;
    byParent.set(key, [...(byParent.get(key) ?? []), node]);
  });
  const build = (parentId: string | null): DataNode[] =>
    (byParent.get(parentId) ?? [])
      .sort((left, right) => left.sort_order - right.sort_order || left.title.localeCompare(right.title, "zh-Hans-CN"))
      .map((node) => {
        const childCount = byParent.get(node.id)?.length ?? 0;
        const isProposal = Boolean(node.metadata?.virtual_proposal);
        return {
          key: node.id,
          title: (
            <span className="settings-tree-title">
              <span>{node.title}</span>
              {node.node_type === "folder" ? <Tag>{childCount}</Tag> : <Tag>{isProposal ? "候选" : refTypeLabels[node.ref_type] ?? node.ref_type}</Tag>}
            </span>
          ),
          children: build(node.id),
        };
      });
  return build(null);
}

function diffContent(previous: Record<string, unknown> | undefined, current: Record<string, unknown>): DiffRow[] {
  const keys = new Set([...Object.keys(previous ?? {}), ...Object.keys(current)]);
  return [...keys]
    .filter((key) => !DIFF_IGNORED_KEYS.has(key))
    .map((key) => ({ field: fieldLabels[key] ?? key, before: normalizeText(previous?.[key]), after: normalizeText(current[key]) }))
    .filter((row) => row.before !== row.after);
}

function isVirtualProposal(node: CanonNode | null): boolean {
  return Boolean(node?.metadata?.virtual_proposal);
}

function isConcreteItem(node: CanonNode | null): node is CanonNode {
  return Boolean(node && node.node_type === "item" && node.ref_type !== "folder" && !isVirtualProposal(node));
}

function RelationSummary({ node, impact, loading }: { node: CanonNode | null; impact?: CanonImpact; loading?: boolean }) {
  const content = node?.content ?? {};
  const relationRows = [
    ["相关人物", content.related_character_ids],
    ["相关实体", content.related_entity_ids],
    ["首次出现章节", content.first_appearance_chapter_id ?? content.source_chapter_id ?? content.planted_chapter_id],
    ["最近出现章节", content.last_seen_chapter_id ?? content.actual_payoff_chapter_id],
    ["计划回收章节", content.planned_payoff_chapter_id],
  ].filter(([, value]) => formatValue(value) !== "未填写");
  return (
    <Space direction="vertical" size={12} className="full-width">
      <Card size="small" title={<Space><Network size={15} />关系与影响范围</Space>}>
        {relationRows.length ? (
          <Descriptions column={1} size="small">
            {relationRows.map(([label, value]) => (
              <Descriptions.Item key={String(label)} label={String(label)}>{formatValue(value)}</Descriptions.Item>
            ))}
          </Descriptions>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无显式关系字段" />
        )}
      </Card>
      <Card size="small" title="影响范围分析" loading={loading}>
        <Space direction="vertical" size={10} className="full-width">
          <Space wrap>
            <Tag>影响章节 {impact?.summary.chapter_count ?? 0}</Tag>
            <Tag>图谱关系 {impact?.summary.relation_count ?? relationRows.length}</Tag>
            <Tag>关联伏笔 {impact?.summary.foreshadowing_count ?? 0}</Tag>
            <Tag>候选记录 {impact?.summary.proposal_count ?? 0}</Tag>
          </Space>
          <List
            size="small"
            dataSource={impact?.chapters ?? []}
            locale={{ emptyText: "暂无章节引用" }}
            renderItem={(chapter) => <List.Item>第 {chapter.chapter_no} 章 · {chapter.title}</List.Item>}
          />
        </Space>
      </Card>
    </Space>
  );
}

function DiffList({ changes }: { changes: DiffRow[] }) {
  if (!changes.length) {
    return <Typography.Text type="secondary">差异对比：与上一版无字段差异。</Typography.Text>;
  }
  return (
    <div className="settings-version-diff">
      <Typography.Text strong>差异对比</Typography.Text>
      {changes.slice(0, 5).map((change) => (
        <div key={change.field} className="settings-diff-row">
          <small>{change.field}</small>
          <span>{change.before}</span>
          <strong>{change.after}</strong>
        </div>
      ))}
      {changes.length > 5 ? <Typography.Text type="secondary">另有 {changes.length - 5} 项字段变化。</Typography.Text> : null}
    </div>
  );
}

function DetailPanel({
  node,
  childCount,
  onToggleLock,
  lockLoading,
}: {
  node: CanonNode | null;
  childCount: number;
  onToggleLock?: (field: string) => void;
  lockLoading?: boolean;
}) {
  if (!node) {
    return (
      <Card className="settings-workbench-card">
        <Empty description="请选择一个设定节点" />
      </Card>
    );
  }
  if (node.node_type === "folder") {
    return (
      <Card className="settings-workbench-card" title={<Space><ListTree size={16} />{node.title}</Space>}>
        <div className="settings-folder-summary">
          <Typography.Text type="secondary">{formatValue(node.metadata?.description)}</Typography.Text>
          <Row gutter={[10, 10]}>
            <Col span={12}><Statistic title="子节点" value={childCount} /></Col>
            <Col span={12}><Statistic title="状态" value={node.activity_status} /></Col>
          </Row>
        </div>
      </Card>
    );
  }
  const content: Record<string, unknown> = node.content ?? {};
  const sourceFields = ["source_chapter_id", "first_appearance_chapter_id", "last_seen_chapter_id", "source", "updated_reason", "source_agent", "source_job_id"].filter((key) => content[key] !== undefined);
  const coreFields = Object.entries(content).filter(([key, value]) => !["id", "project_id", "created_at", "updated_at", "related_entity_ids", "related_character_ids", "before"].includes(key) && !sourceFields.includes(key) && value !== "");
  const relationFields = ["related_entity_ids", "related_character_ids"].filter((key) => Array.isArray(content[key]) && (content[key] as unknown[]).length > 0);
  const isCharacter = node.ref_type === "character";
  const isProposal = isVirtualProposal(node);
  const lockedFields = Array.isArray(node.metadata?.locked_fields) ? (node.metadata.locked_fields as string[]) : [];
  const availableLockFields = LOCKABLE_FIELDS.filter((field) => field in content || ["summary", "secrets", "character_arc", "content", "description", "planned_payoff"].includes(field));
  return (
    <Card
      className="settings-workbench-card"
      title={<Space><ShieldCheck size={16} />{node.title}</Space>}
      extra={<Space><Tag>{isProposal ? "候选变更" : refTypeLabels[node.ref_type]}</Tag><Badge status={node.activity_status === "archived" ? "default" : "processing"} text={node.activity_status} /></Space>}
    >
      <Descriptions column={1} size="small" className="settings-detail-list">
        {coreFields.slice(0, 12).map(([key, value]) => (
          <Descriptions.Item key={key} label={fieldLabels[key] ?? key}>{formatValue(value)}</Descriptions.Item>
        ))}
      </Descriptions>

      {isCharacter ? (
        <div className="settings-character-card">
          <Typography.Text strong>人物卡当前状态</Typography.Text>
          <div className="settings-status-grid">
            {[
              ["身份", content.role_type ?? content.summary],
              ["目标", content.goals],
              ["动机", content.motivations],
              ["伤口", content.weaknesses],
              ["秘密", content.secrets],
              ["能力", content.abilities],
              ["关系", content.related_character_ids],
              ["当前处境", content.current_status ?? content.summary],
            ].map(([label, value]) => (
              <span key={String(label)}>
                <small>{String(label)}</small>
                <strong>{formatValue(value)}</strong>
              </span>
            ))}
          </div>
        </div>
      ) : null}

      <div className="settings-freeze-panel">
        <Space size={6}><Lock size={14} /><Typography.Text strong>冻结字段</Typography.Text></Space>
        <Space wrap>
          {availableLockFields.map((field) => {
            const locked = lockedFields.includes(field);
            return (
              <Button
                key={field}
                size="small"
                type={locked ? "primary" : "default"}
                loading={lockLoading}
                disabled={isProposal || !onToggleLock}
                onClick={() => onToggleLock?.(field)}
              >
                {fieldLabels[field] ?? field}{locked ? " 已锁" : ""}
              </Button>
            );
          })}
        </Space>
        <Typography.Text type="secondary">锁定项走候选审批，不静默覆盖正式设定。</Typography.Text>
      </div>

      <div className="settings-impact-panel">
        <Typography.Text strong>来源与影响索引</Typography.Text>
        <div className="settings-impact-grid">
          {sourceFields.map((key) => (
            <span key={key}><small>{fieldLabels[key] ?? key}</small><strong>{formatValue(content[key])}</strong></span>
          ))}
          {relationFields.map((key) => (
            <span key={key}><small>{fieldLabels[key] ?? key}</small><strong>{formatValue(content[key])}</strong></span>
          ))}
          {sourceFields.length === 0 && relationFields.length === 0 ? <Typography.Text type="secondary">暂无章节来源或关系引用。</Typography.Text> : null}
        </div>
      </div>
    </Card>
  );
}

export function SettingsWorkbenchPage() {
  const { projectId = "" } = useParams();
  const queryClient = useQueryClient();
  const [selectedKey, setSelectedKey] = useState<string>("");
  const [folderModalOpen, setFolderModalOpen] = useState(false);
  const [folderTitle, setFolderTitle] = useState("");
  const treeQuery = useQuery({ queryKey: ["settings-tree", projectId], queryFn: () => studioApi.getSettingsTree(projectId), enabled: !!projectId });
  const proposalsQuery = useQuery({ queryKey: ["canon-proposals", projectId, "pending"], queryFn: () => studioApi.listCanonProposals(projectId, "pending"), enabled: !!projectId });
  const displayNodes = useMemo(() => buildDisplayNodes(treeQuery.data?.nodes ?? [], proposalsQuery.data?.proposals ?? []), [treeQuery.data?.nodes, proposalsQuery.data?.proposals]);
  const health = treeQuery.data?.health;
  const selectedNode = displayNodes.find((node) => node.id === selectedKey) ?? null;
  const treeData = useMemo(() => buildTreeData(displayNodes), [displayNodes]);
  const childCount = useMemo(() => displayNodes.filter((node) => node.parent_id === selectedNode?.id).length, [displayNodes, selectedNode?.id]);
  const itemNode = isConcreteItem(selectedNode) ? selectedNode : null;
  const versionsQuery = useQuery({
    queryKey: ["canon-versions", projectId, itemNode?.ref_type, itemNode?.ref_id],
    queryFn: () => studioApi.listCanonVersions(projectId, itemNode?.ref_type ?? "", itemNode?.ref_id ?? ""),
    enabled: !!projectId && !!itemNode,
  });
  const impactQuery = useQuery({
    queryKey: ["canon-impact", projectId, itemNode?.ref_type, itemNode?.ref_id],
    queryFn: () => studioApi.getCanonImpact(projectId, itemNode?.ref_type ?? "", itemNode?.ref_id ?? ""),
    enabled: !!projectId && !!itemNode,
  });
  const versions = useMemo(() => [...(versionsQuery.data?.versions ?? [])].sort((left, right) => left.version_no - right.version_no), [versionsQuery.data?.versions]);
  const latestVersion = versions[versions.length - 1];

  useEffect(() => {
    if (!selectedKey && displayNodes.length) {
      const firstItem = displayNodes.find((node) => node.node_type === "item" && !isVirtualProposal(node)) ?? displayNodes[0];
      setSelectedKey(firstItem.id);
    }
  }, [displayNodes, selectedKey]);

  const invalidateWorkbench = () => {
    queryClient.invalidateQueries({ queryKey: ["settings-tree", projectId] });
    queryClient.invalidateQueries({ queryKey: ["canon-proposals", projectId] });
    queryClient.invalidateQueries({ queryKey: ["canon-versions", projectId] });
    queryClient.invalidateQueries({ queryKey: ["canon-impact", projectId] });
    queryClient.invalidateQueries({ queryKey: ["characters", projectId] });
    queryClient.invalidateQueries({ queryKey: ["entities", projectId] });
    queryClient.invalidateQueries({ queryKey: ["world", projectId] });
    queryClient.invalidateQueries({ queryKey: ["graph", projectId] });
    queryClient.invalidateQueries({ queryKey: ["foreshadowing", projectId] });
  };

  const rollbackMutation = useMutation({
    mutationFn: (version: CanonVersion) => {
      if (!itemNode) throw new Error("请选择可回滚的设定");
      return studioApi.rollbackCanonVersion(projectId, itemNode.ref_type, itemNode.ref_id, version.id, `回滚到版本 ${version.version_no}`);
    },
    onSuccess: () => {
      message.success("设定已回滚，并生成新的版本记录");
      invalidateWorkbench();
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "回滚失败"),
  });

  const approveMutation = useMutation({
    mutationFn: (proposal: CanonChangeProposal) => studioApi.approveCanonProposal(projectId, proposal.id, "从设定文件树审批通过"),
    onSuccess: () => {
      message.success("候选设定已写入正式设定集");
      invalidateWorkbench();
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "审批失败"),
  });

  const rejectMutation = useMutation({
    mutationFn: (proposal: CanonChangeProposal) => studioApi.rejectCanonProposal(projectId, proposal.id, "从设定文件树驳回"),
    onSuccess: () => {
      message.success("候选设定已驳回");
      invalidateWorkbench();
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "驳回失败"),
  });

  const archiveMutation = useMutation({
    mutationFn: () => {
      if (!itemNode) throw new Error("请选择可归档的设定");
      return studioApi.archiveCanonItems(projectId, { ref_type: itemNode.ref_type, ref_ids: [itemNode.ref_id], reason: "从设定文件树归档" });
    },
    onSuccess: () => {
      message.success("设定已归档");
      invalidateWorkbench();
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "归档失败"),
  });

  const createFolderMutation = useMutation({
    mutationFn: () => {
      const parentId = selectedNode?.node_type === "folder" ? selectedNode.id : selectedNode?.parent_id ?? "folder:root";
      return studioApi.createCanonFolder(projectId, { title: folderTitle.trim(), parent_id: parentId, sort_order: childCount + 1 });
    },
    onSuccess: () => {
      message.success("文件夹已创建");
      setFolderTitle("");
      setFolderModalOpen(false);
      invalidateWorkbench();
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "创建文件夹失败"),
  });

  const moveNodeMutation = useMutation({
    mutationFn: ({ nodeId, parentId, sortOrder }: { nodeId: string; parentId: string; sortOrder: number }) =>
      studioApi.moveCanonNode(projectId, nodeId, { parent_id: parentId, sort_order: sortOrder }),
    onSuccess: () => {
      message.success("设定节点已移动");
      invalidateWorkbench();
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "移动失败"),
  });

  const lockMutation = useMutation({
    mutationFn: ({ field, lockedFields }: { field: string; lockedFields: string[] }) => {
      if (!itemNode) throw new Error("请选择正式设定");
      const nextFields = lockedFields.includes(field) ? lockedFields.filter((item) => item !== field) : [...lockedFields, field];
      return studioApi.setCanonLocks(projectId, itemNode.ref_type, itemNode.ref_id, { locked_fields: nextFields, reason: "从设定文件树调整锁定字段" });
    },
    onSuccess: () => {
      message.success("锁定字段已更新");
      invalidateWorkbench();
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "锁定失败"),
  });

  const duplicateScanMutation = useMutation({
    mutationFn: () => studioApi.scanCanonDuplicates(projectId, { threshold: 0.72, create_proposals: true }),
    onSuccess: (data) => {
      message.success(`重复扫描完成，发现 ${data.candidates.length} 组，生成 ${data.proposals.length} 条合并候选`);
      invalidateWorkbench();
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "重复扫描失败"),
  });

  const exportMutation = useMutation({
    mutationFn: (format: "json" | "markdown") => studioApi.exportCanonPackage(projectId, format),
    onSuccess: (data) => {
      downloadTextFile(data.filename, data.content, data.format === "json" ? "application/json;charset=utf-8" : "text/markdown;charset=utf-8");
      message.success("正典包已导出");
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "导出失败"),
  });

  const sourceRows = [
    ["当前版本", latestVersion ? `v${latestVersion.version_no}` : "未版本化"],
    ["来源章节", selectedNode?.content?.source_chapter_id ?? latestVersion?.source_chapter_id],
    ["首次出现", selectedNode?.content?.first_appearance_chapter_id],
    ["最近出现", selectedNode?.content?.last_seen_chapter_id],
    ["来源任务", selectedNode?.content?.source_job_id ?? latestVersion?.source_job_id],
    ["来源 Agent", selectedNode?.content?.source_agent ?? latestVersion?.source_agent],
    ["变更原因", selectedNode?.content?.updated_reason ?? latestVersion?.change_reason],
  ];
  const versionCoverage = health?.official_count ? Math.round(((health.versioned_count ?? 0) / health.official_count) * 100) : 0;
  const selectedLockedFields = Array.isArray(itemNode?.metadata?.locked_fields) ? (itemNode?.metadata.locked_fields as string[]) : [];
  const handleTreeDrop = (info: { dragNode: { key: Key }; node: { key: Key }; dropToGap: boolean }) => {
    const dragKey = String(info.dragNode.key);
    const dropKey = String(info.node.key);
    const dragged = displayNodes.find((node) => node.id === dragKey);
    const dropped = displayNodes.find((node) => node.id === dropKey);
    if (!dragged || !dropped || dragged.metadata?.virtual || isVirtualProposal(dragged)) {
      message.warning("只能移动正式设定或自定义文件夹");
      return;
    }
    const parentId = info.dropToGap ? dropped.parent_id ?? "folder:root" : dropped.node_type === "folder" ? dropped.id : dropped.parent_id ?? "folder:root";
    moveNodeMutation.mutate({ nodeId: dragged.id, parentId, sortOrder: (dropped.sort_order ?? 0) + 1 });
  };

  return (
    <Space direction="vertical" size={18} className="page-stack">
      <SettingsSectionNav active="tree" />
      <div className="page-heading">
        <div>
          <Typography.Title level={3}>设定文件树</Typography.Title>
          <Typography.Text type="secondary">统一管理正典设定集、候选变更、版本历史、来源章节、关系索引和 Agent 更新记录。</Typography.Text>
        </div>
        <Space wrap>
          <Button icon={<FolderPlus size={15} />} onClick={() => setFolderModalOpen(true)}>
            新建文件夹
          </Button>
          <Button icon={<Search size={15} />} loading={duplicateScanMutation.isPending} onClick={() => duplicateScanMutation.mutate()}>
            扫描重复项
          </Button>
          <Button icon={<Download size={15} />} loading={exportMutation.isPending} onClick={() => exportMutation.mutate("markdown")}>
            导出 Markdown
          </Button>
          <Button icon={<Download size={15} />} loading={exportMutation.isPending} onClick={() => exportMutation.mutate("json")}>
            导出 JSON
          </Button>
          <Button icon={<Archive size={15} />} disabled={!itemNode} loading={archiveMutation.isPending} onClick={() => {
            Modal.confirm({
              title: "归档当前设定？",
              content: itemNode ? `确认归档「${itemNode.title}」吗？会保留版本记录。` : "",
              okText: "归档",
              cancelText: "取消",
              onOk: () => archiveMutation.mutate(),
            });
          }}>
            归档
          </Button>
        </Space>
      </div>
      {treeQuery.error ? <Alert type="error" showIcon message="无法读取设定文件树" description={(treeQuery.error as Error).message} /> : null}
      <Modal
        title="新建自定义文件夹"
        open={folderModalOpen}
        okText="创建"
        cancelText="取消"
        confirmLoading={createFolderMutation.isPending}
        onCancel={() => setFolderModalOpen(false)}
        onOk={() => {
          if (!folderTitle.trim()) {
            message.warning("请输入文件夹名称");
            return;
          }
          createFolderMutation.mutate();
        }}
      >
        <Space direction="vertical" size={10} className="full-width">
          <Typography.Text type="secondary">新文件夹会创建在当前选中的目录下；如果当前选中的是设定要素，则创建在它所在目录。</Typography.Text>
          <Input value={folderTitle} onChange={(event) => setFolderTitle(event.target.value)} placeholder="例如：第一卷核心人物" maxLength={120} />
        </Space>
      </Modal>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={7}>
          <Card className="settings-tree-card" title={<Space><ListTree size={16} />正典目录</Space>} loading={treeQuery.isLoading || proposalsQuery.isLoading}>
            {treeData.length ? (
              <Tree
                blockNode
                draggable={{ icon: false }}
                defaultExpandAll
                selectedKeys={selectedKey ? [selectedKey] : []}
                treeData={treeData}
                onDrop={handleTreeDrop}
                onSelect={(keys) => setSelectedKey(String(keys[0] ?? ""))}
              />
            ) : (
              <Empty description="暂无设定节点" />
            )}
          </Card>
        </Col>

        <Col xs={24} xl={10}>
          <DetailPanel
            node={selectedNode}
            childCount={childCount}
            lockLoading={lockMutation.isPending}
            onToggleLock={(field) => lockMutation.mutate({ field, lockedFields: selectedLockedFields })}
          />
        </Col>

        <Col xs={24} xl={7}>
          <Tabs
            className="settings-side-tabs"
            items={[
              {
                key: "versions",
                label: "版本",
                children: (
                  <List
                    loading={versionsQuery.isLoading}
                    dataSource={versions}
                    locale={{ emptyText: itemNode ? "暂无版本记录" : "请选择一个正式设定节点" }}
                    renderItem={(version, index) => {
                      const changes = diffContent(versions[index - 1]?.content, version.content);
                      return (
                        <List.Item
                          actions={[
                            <Tooltip key="rollback" title="回滚到此版本">
                              <Button
                                size="small"
                                icon={<RotateCcw size={14} />}
                                loading={rollbackMutation.isPending}
                                onClick={() => {
                                  Modal.confirm({
                                    title: `回滚到版本 ${version.version_no}？`,
                                    content: "系统会先应用旧内容，再创建一条新的回滚版本记录。",
                                    okText: "回滚",
                                    cancelText: "取消",
                                    onOk: () => rollbackMutation.mutate(version),
                                  });
                                }}
                              />
                            </Tooltip>,
                          ]}
                        >
                          <List.Item.Meta
                            avatar={<Clock3 size={18} />}
                            title={<Space><span>v{version.version_no}</span><Tag>{version.source_agent}</Tag></Space>}
                            description={
                              <Space direction="vertical" size={6} className="full-width">
                                <Typography.Text>{versionTitle(version)}</Typography.Text>
                                <Typography.Text type="secondary">来源章节：{version.source_chapter_id || "未绑定"} · {version.change_reason || "无说明"}</Typography.Text>
                                <DiffList changes={changes} />
                              </Space>
                            }
                          />
                        </List.Item>
                      );
                    }}
                  />
                ),
              },
              {
                key: "source",
                label: "来源",
                children: (
                  <Card size="small" title="章节来源索引">
                    <Descriptions column={1} size="small">
                      {sourceRows.map(([label, value]) => (
                        <Descriptions.Item key={String(label)} label={String(label)}>{formatValue(value)}</Descriptions.Item>
                      ))}
                    </Descriptions>
                  </Card>
                ),
              },
              {
                key: "relations",
                label: "关系",
                children: <RelationSummary node={selectedNode} impact={impactQuery.data} loading={impactQuery.isLoading} />,
              },
              {
                key: "evolution",
                label: "状态演进",
                children: (
                  <List
                    dataSource={versions}
                    locale={{ emptyText: itemNode ? "暂无状态演进记录" : "请选择一个正式设定节点" }}
                    renderItem={(version) => (
                      <List.Item>
                        <List.Item.Meta
                          avatar={<History size={18} />}
                          title={`第 ${version.source_chapter_id || "未知"} 章 · v${version.version_no}`}
                          description={version.change_reason || versionTitle(version)}
                        />
                      </List.Item>
                    )}
                  />
                ),
              },
              {
                key: "audit",
                label: "Agent 审计",
                children: (
                  <List
                    dataSource={[
                      ...versions.map((version) => ({
                        id: version.id,
                        title: `v${version.version_no} · ${version.source_agent}`,
                        detail: `${version.change_reason || "版本更新"} · 置信度 ${Math.round(version.confidence * 100)}% · 任务 ${version.source_job_id || "未绑定"}`,
                      })),
                      ...(proposalsQuery.data?.proposals ?? []).slice(0, 6).map((proposal) => ({
                        id: proposal.id,
                        title: `候选 · ${proposal.source_agent}`,
                        detail: `${proposal.reason || proposal.operation} · 置信度 ${Math.round(proposal.confidence * 100)}%`,
                      })),
                    ]}
                    locale={{ emptyText: "暂无 Agent 更新记录" }}
                    renderItem={(item) => (
                      <List.Item>
                        <List.Item.Meta avatar={<GitCompare size={18} />} title={item.title} description={item.detail} />
                      </List.Item>
                    )}
                  />
                ),
              },
              {
                key: "duplicates",
                label: "重复项",
                children: (
                  <Space direction="vertical" size={12} className="full-width">
                    <Button block icon={<GitMerge size={15} />} loading={duplicateScanMutation.isPending} onClick={() => duplicateScanMutation.mutate()}>
                      扫描并生成合并候选
                    </Button>
                    <List
                      dataSource={duplicateScanMutation.data?.candidates ?? []}
                      locale={{ emptyText: "暂无重复扫描结果" }}
                      renderItem={(candidate) => (
                        <List.Item>
                          <List.Item.Meta
                            avatar={<GitMerge size={18} />}
                            title={`${candidate.source.title} → ${candidate.target.title}`}
                            description={`相似度 ${Math.round(candidate.score * 100)}% · ${candidate.reason}`}
                          />
                        </List.Item>
                      )}
                    />
                  </Space>
                ),
              },
              {
                key: "proposals",
                label: "候选",
                children: (
                  <List
                    loading={proposalsQuery.isLoading}
                    dataSource={proposalsQuery.data?.proposals ?? []}
                    locale={{ emptyText: "暂无待审批候选" }}
                    renderItem={(proposal) => (
                      <List.Item
                        actions={[
                          <Button key="approve" size="small" type="primary" icon={<Check size={14} />} loading={approveMutation.isPending} onClick={() => approveMutation.mutate(proposal)}>通过</Button>,
                          <Button key="reject" size="small" icon={<X size={14} />} loading={rejectMutation.isPending} onClick={() => rejectMutation.mutate(proposal)}>驳回</Button>,
                        ]}
                      >
                        <List.Item.Meta
                          avatar={<GitCompare size={18} />}
                          title={<Space><span>{proposalTitle(proposal)}</span><Tag>{proposal.operation}</Tag><Tag>{refTypeLabels[proposal.target_type]}</Tag></Space>}
                          description={<Typography.Text type="secondary">{proposal.reason || "Agent 候选变更"} · 置信度 {Math.round(proposal.confidence * 100)}%</Typography.Text>}
                        />
                      </List.Item>
                    )}
                  />
                ),
              },
              {
                key: "health",
                label: "健康度",
                children: (
                  <Space direction="vertical" size={12} className="full-width">
                    <Card size="small" title="正典健康度仪表盘">
                      <Progress percent={versionCoverage} size="small" />
                      <Typography.Text type="secondary">版本覆盖率：{health?.versioned_count ?? 0}/{health?.official_count ?? 0}</Typography.Text>
                    </Card>
                    <Row gutter={[10, 10]}>
                      <Col span={12}><Card><Statistic title="正式设定" value={health?.official_count ?? 0} /></Card></Col>
                      <Col span={12}><Card><Statistic title="已版本化" value={health?.versioned_count ?? 0} /></Card></Col>
                      <Col span={12}><Card><Statistic title="待审批" value={health?.pending_proposal_count ?? 0} /></Card></Col>
                      <Col span={12}><Card><Statistic title="低置信度" value={health?.low_confidence_count ?? 0} /></Card></Col>
                    </Row>
                    <Card size="small" title="分类统计">
                      <Space wrap>
                        <Tag>人物 {health?.by_type.characters ?? 0}</Tag>
                        <Tag>实体 {health?.by_type.entities ?? 0}</Tag>
                        <Tag>事实 {health?.by_type.world_facts ?? 0}</Tag>
                        <Tag>伏笔 {health?.by_type.foreshadowing ?? 0}</Tag>
                      </Space>
                    </Card>
                    <Card size="small" title="冲突告警">
                      <Badge status={(health?.conflict_count ?? 0) > 0 ? "error" : "success"} text={`当前冲突 ${health?.conflict_count ?? 0} 项`} />
                    </Card>
                  </Space>
                ),
              },
            ]}
          />
        </Col>
      </Row>
    </Space>
  );
}
