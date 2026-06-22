import { App, Button, Empty, Mentions, Segmented, Space, Switch, Tag, Timeline, Typography } from "antd";
import { ArrowDown, BookOpen, CheckCircle2, Layers, ListTree, MessageSquare, PauseCircle, Play, Radio, RefreshCw, StepForward } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { studioApi, streamOutlineDebatePhase } from "../../api/studio";
import type { ScalePlan } from "../../types/api";
import type {
  OutlineDebatePhase,
  OutlineDebatePhaseRun,
  OutlineDebateSession,
  OutlineDebateStreamEvent,
  OutlineDebateUserMessage,
} from "../../api/studio";
import type { OutlineView } from "./types";

interface OutlineDebatePanelProps {
  projectId: string;
  defaultRequirement: string;
  volumeCount: number;
  chaptersPerVolume: number;
  targetWords?: number;
  chapterWordTarget?: number;
  chapterWordMin?: number;
  chapterWordMax?: number;
  scalePlan?: ScalePlan;
  selectedVolumeNo?: number;
  selectedChapterNo?: number;
  selectedView?: OutlineView;
  useTopologyInference?: boolean;
  compact?: boolean;
  onPhaseComplete?: (phaseRun: OutlineDebatePhaseRun) => void;
  onFormalCommit?: () => void;
}

const phaseLabels: Record<OutlineDebatePhase, string> = {
  book: "讨论总纲",
  volumes: "讨论卷纲",
  chapters: "讨论章纲",
};

const confirmActionLabels: Record<OutlineDebatePhase, string> = {
  book: "确认总纲",
  volumes: "确认本卷",
  chapters: "确认本章",
};

const phaseIcons: Record<OutlineDebatePhase, ReactNode> = {
  book: <BookOpen size={14} />,
  volumes: <Layers size={14} />,
  chapters: <ListTree size={14} />,
};

const debateAgents = [
  { value: "主持总策划", label: "主持总策划", agentName: "outline_debate/StoryDirectorAgent" },
  { value: "类型卖点", label: "类型卖点", agentName: "outline_debate/MarketPositionAgent" },
  { value: "结构医生", label: "结构医生", agentName: "outline_debate/StructureDoctorAgent" },
  { value: "角色生成", label: "角色生成", agentName: "outline_debate/CharacterGeneratorAgent" },
  { value: "设定生成", label: "设定生成", agentName: "outline_debate/SettingGeneratorAgent" },
  { value: "连续性审计", label: "连续性审计", agentName: "outline_debate/ContinuityAuditorAgent" },
];

function eventTitle(event: OutlineDebateStreamEvent) {
  if (event.type === "meta") return event.message;
  if (event.type === "user_message") return `用户意见${event.message.target_agent_name ? " → " + agentDisplayName(event.message.target_agent_name) : ""}`;
  if (event.type === "turn") return `${event.turn.role}：${event.turn.stance}`;
  if (event.type === "pause") return "等待用户继续";
  if (event.type === "interrupt") return "议事已打断";
  if (event.type === "decision") return `决议：${event.decision.title}`;
  if (event.type === "artifact") return `生成待确认条目：${event.artifact.title}`;
  return `${phaseLabels[event.phase]}完成`;
}

function eventDescription(event: OutlineDebateStreamEvent) {
  if (event.type === "user_message") return event.message.message;
  if (event.type === "turn") return event.turn.display_text !== undefined ? event.turn.display_text : event.turn.message;
  if (event.type === "pause") return event.next_agent_name ? `下一位：${agentDisplayName(event.next_agent_name)}` : event.message;
  if (event.type === "interrupt") return event.message;
  if (event.type === "decision") return event.decision.decision;
  if (event.type === "artifact") return `${event.artifact.type} · 待确认 → 确认即入正典`;
  if (event.type === "done") return "阶段结果已保存到大纲议事会话。";
  return "后端正在发送真实 Agent 议事流。";
}

function eventColor(event: OutlineDebateStreamEvent) {
  if (event.type === "done") return "green";
  if (event.type === "pause") return "orange";
  if (event.type === "interrupt") return "red";
  if (event.type === "user_message") return "purple";
  if (event.type === "artifact") return "gold";
  if (event.type === "decision") return "blue";
  return "gray";
}

function agentDisplayName(agentName: string) {
  return debateAgents.find((agent) => agent.agentName === agentName)?.label ?? agentName.replace("outline_debate/", "");
}

function detectTargetAgent(value: string) {
  return debateAgents.find((agent) => value.includes(`@${agent.value}`))?.agentName ?? "";
}

function compactNumber(value?: number) {
  const numeric = Number(value || 0);
  return numeric > 0 ? numeric.toLocaleString("zh-CN") : "未设定";
}

function phaseStatus(session: OutlineDebateSession | null, phase: OutlineDebatePhase, fullyConfirmed = false) {
  const run = session?.phase_runs?.[phase];
  if (run?.candidate_status === "confirmed" && !fullyConfirmed && phase !== "book") return <Tag color="lime">部分确认</Tag>;
  if (run?.candidate_status === "confirmed") return <Tag color="green">已确认</Tag>;
  if (run?.candidate_status === "partially_confirmed") return <Tag color="lime">部分确认</Tag>;
  if (run?.candidate_status === "stale") return <Tag color="red">已过期</Tag>;
  if (run?.candidate_status === "pending_confirmation") return <Tag color="gold">待确认</Tag>;
  if (run?.status === "succeeded") return <Tag color="green">已讨论</Tag>;
  if (run?.status === "paused") return <Tag color="orange">暂停中</Tag>;
  if (run?.status === "interrupted") return <Tag color="red">已打断</Tag>;
  return <Tag>未讨论</Tag>;
}

function candidateStatusLabel(status?: string) {
  if (status === "confirmed") return { color: "green", text: "已确认" };
  if (status === "partially_confirmed") return { color: "lime", text: "部分确认" };
  if (status === "stale") return { color: "red", text: "已过期" };
  if (status === "pending_confirmation") return { color: "gold", text: "待确认" };
  if (status === "draft") return { color: "default", text: "草稿" };
  return { color: "default", text: "未生成" };
}

function shouldShowRoundSeparator(events: OutlineDebateStreamEvent[], index: number, event: OutlineDebateStreamEvent) {
  if (event.type !== "turn") return false;
  const previousTurn = events
    .slice(0, index)
    .reverse()
    .find((item): item is Extract<OutlineDebateStreamEvent, { type: "turn" }> => item.type === "turn");
  return !previousTurn || previousTurn.turn.round_no !== event.turn.round_no;
}

function emptyStreamingTurn(turn: Extract<OutlineDebateStreamEvent, { type: "turn" }>["turn"]) {
  return { ...turn, display_text: "" };
}

function eventsFromPhaseRun(session: OutlineDebateSession | null, phase: OutlineDebatePhase): OutlineDebateStreamEvent[] {
  if (!session) return [];
  const run = session.phase_runs?.[phase];
  if (!run) return [];
  const events: OutlineDebateStreamEvent[] = [];
  (run.user_messages ?? [])
    .filter((item) => item.role === "user")
    .forEach((item) => events.push({ type: "user_message", phase, message: item, session }));
  (run.turns ?? []).forEach((turn) => events.push({ type: "turn", phase, turn }));
  if (run.status === "succeeded") {
    (run.decisions ?? []).forEach((decision) => events.push({ type: "decision", phase, decision }));
    (run.artifacts ?? []).forEach((artifact) => events.push({ type: "artifact", phase, artifact }));
    events.push({ type: "done", phase, phase_run: run, session });
  }
  if (run.status === "paused") {
    events.push({
      type: "pause",
      phase,
      message: "当前 Agent 发言完成，等待用户继续或发表意见。",
      next_agent_name: run.next_agent_name,
      phase_run: run,
      session,
    });
  }
  return events;
}

export function OutlineDebatePanel({
  projectId,
  defaultRequirement,
  volumeCount,
  chaptersPerVolume,
  targetWords,
  chapterWordTarget,
  chapterWordMin,
  chapterWordMax,
  scalePlan,
  selectedVolumeNo = 1,
  selectedChapterNo = 1,
  selectedView = "outline",
  useTopologyInference = true,
  compact = false,
  onPhaseComplete,
  onFormalCommit,
}: OutlineDebatePanelProps) {
  const { message } = App.useApp();
  const [session, setSession] = useState<OutlineDebateSession | null>(null);
  const [activePhase, setActivePhase] = useState<OutlineDebatePhase>("book");
  const [joinDiscussion, setJoinDiscussion] = useState(false);
  const [userMessage, setUserMessage] = useState("");
  const [events, setEvents] = useState<OutlineDebateStreamEvent[]>([]);
  const [runningPhase, setRunningPhase] = useState<OutlineDebatePhase | null>(null);
  const [userPinnedToLatest, setUserPinnedToLatest] = useState(true);
  const abortRef = useRef<AbortController | null>(null);
  const streamViewportRef = useRef<HTMLDivElement | null>(null);
  const streamEndRef = useRef<HTMLDivElement | null>(null);
  const lastSelectedViewRef = useRef(selectedView);
  const activeRun = session?.phase_runs?.[activePhase] ?? null;
  const paused = activeRun?.status === "paused";
  const running = runningPhase !== null;
  const hasPendingUserMessage = useMemo(() => {
    const messages = [
      ...(activeRun?.user_messages ?? []),
      ...((session?.messages ?? []).filter((item) => item.phase === activePhase)),
    ];
    const seen = new Set<string>();
    return messages.some((item) => {
      if (item.id && seen.has(item.id)) return false;
      if (item.id) seen.add(item.id);
      return item.role === "user" && !item.handled_by_turn_id;
    });
  }, [activePhase, activeRun?.user_messages, session?.messages]);
  const latestTurn = useMemo(
    () => [...events].reverse().find((event): event is Extract<OutlineDebateStreamEvent, { type: "turn" }> => event.type === "turn"),
    [events],
  );
  const currentSpeakerName = running ? latestTurn?.turn.agent_name || activeRun?.next_agent_name || "" : "";
  const currentSpeakerLabel = currentSpeakerName ? agentDisplayName(currentSpeakerName) : "";
  const activeCandidateStatus = candidateStatusLabel(activeRun?.candidate_status);
  const activeItemKey = activePhase === "volumes" ? `volume:${selectedVolumeNo}` : activePhase === "chapters" ? `chapter:${selectedChapterNo}` : "";
  const activeConfirmationItem = activeItemKey ? activeRun?.confirmation_items?.find((item) => item.item_key === activeItemKey) : undefined;
  const activeItemAlreadyConfirmed = Boolean(activeItemKey && activeConfirmationItem?.candidate_status === "confirmed");
  const confirmedRefreshBlocked = Boolean(activePhase === "book" ? activeRun?.candidate_status === "confirmed" : activeItemAlreadyConfirmed);
  const summaryTargetWords = Number(scalePlan?.target_words || targetWords || 0);
  const summaryVolumeCount = Number(scalePlan?.volume_count || volumeCount || 0);
  const summaryChapterCount = Number(scalePlan?.chapter_count || summaryVolumeCount * (scalePlan?.chapters_per_volume || chaptersPerVolume || 0));
  const summaryChapterTarget = Number(scalePlan?.chapter_word_target || chapterWordTarget || 0);
  const canConfirmActivePhase = Boolean(
    session &&
      activeRun?.status === "succeeded" &&
      !running &&
      (activePhase === "book"
        ? activeRun.candidate_status === "pending_confirmation"
        : activeConfirmationItem?.candidate_status === "pending_confirmation" || activeRun.candidate_status === "pending_confirmation"),
  );
  const phaseFullyConfirmed = (phase: OutlineDebatePhase) => {
    const run = session?.phase_runs?.[phase];
    if (!run || run.candidate_status !== "confirmed" || !session?.confirmed_candidates?.[phase]) return false;
    if (phase === "book") return true;
    const plannedCount =
      phase === "volumes"
        ? Math.max(1, Number(scalePlan?.volume_count || volumeCount || 1))
        : Math.max(1, Number(scalePlan?.chapter_count || (volumeCount || 1) * (chaptersPerVolume || 1)));
    const expectedCount = Math.max(plannedCount, Number(run.expected_item_count || 0), run.confirmation_items?.length || 0);
    const confirmedCount = (run.confirmation_items ?? []).filter((item) => item.candidate_status === "confirmed").length;
    return confirmedCount >= expectedCount;
  };
  const allCandidatesConfirmed = Boolean(session && (["book", "volumes", "chapters"] as OutlineDebatePhase[]).every(phaseFullyConfirmed));
  const formalCommitStatus = session?.formal_commit?.status;
  const alreadyCommitted = session?.status === "committed" || formalCommitStatus === "committed";

  const scrollToLatest = () => {
    setUserPinnedToLatest(true);
    window.requestAnimationFrame(() => streamEndRef.current?.scrollIntoView({ block: "end" }));
  };

  const handleStreamScroll = () => {
    const viewport = streamViewportRef.current;
    if (!viewport) return;
    const nearBottom = viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight < 36;
    setUserPinnedToLatest((current) => (current === nearBottom ? current : nearBottom));
  };

  useEffect(() => {
    if (userPinnedToLatest) streamEndRef.current?.scrollIntoView({ block: "end" });
  }, [events.length, running, userPinnedToLatest]);

  useEffect(() => {
    let cancelled = false;
    setSession(null);
    setEvents([]);
    studioApi
      .createOutlineDebateSession(projectId, {
        idempotency_key: `outline-debate-workspace:${projectId}:v1`,
        brief: defaultRequirement || "三阶段大纲议事",
      })
      .then((result) => {
        if (cancelled) return;
        setSession(result.session);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [defaultRequirement, projectId]);

  useEffect(() => {
    if (running) return;
    setEvents(eventsFromPhaseRun(session, activePhase));
  }, [activePhase, running, session]);

  useEffect(() => {
    if (running || selectedView === lastSelectedViewRef.current) return;
    lastSelectedViewRef.current = selectedView;
    const nextPhase: OutlineDebatePhase =
      selectedView === "volume" ? "volumes" : selectedView === "chapter" || selectedView === "chapterOutline" ? "chapters" : "book";
    setActivePhase((current) => (current === nextPhase ? current : nextPhase));
  }, [running, selectedView]);

  const ensureSession = async () => {
    if (session) return session;
    const result = await studioApi.createOutlineDebateSession(projectId, {
      idempotency_key: `outline-debate-workspace:${projectId}:v1`,
      brief: defaultRequirement || "三阶段大纲议事",
    });
    setSession(result.session);
    return result.session;
  };

  const appendUserMessageEvent = (savedMessage: OutlineDebateUserMessage, nextSession: OutlineDebateSession) => {
    setEvents((current) => [...current, { type: "user_message", phase: activePhase, message: savedMessage, session: nextSession }]);
  };

  const appendTurnDelta = (turnId: string, text: string) => {
    if (!text) return;
    setEvents((current) =>
      current.map((item) => {
        if (item.type !== "turn" || item.turn.id !== turnId) return item;
        return {
          ...item,
          turn: {
            ...item.turn,
            display_text: `${item.turn.display_text || ""}${text}`,
          },
        };
      }),
    );
  };

  const pushStreamEvent = (event: OutlineDebateStreamEvent) => {
    if (event.type === "delta") {
      appendTurnDelta(event.turn_id, event.text);
      return;
    }
    if (event.type === "turn") {
      setEvents((current) => [...current, { ...event, turn: emptyStreamingTurn(event.turn) }]);
      return;
    }
    setEvents((current) => [...current, event]);
  };

  const runActivePhase = async (options: { refreshPhase?: boolean; finishPhase?: boolean } = {}) => {
    if (!projectId) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const refreshPhase = options.refreshPhase ?? true;
    if (refreshPhase) setEvents([]);
    setUserPinnedToLatest(true);
    setRunningPhase(activePhase);
    let finalEventType = "";
    try {
      const currentSession = await ensureSession();
      const startChapter = Math.max(1, selectedChapterNo);
      await streamOutlineDebatePhase(
        projectId,
        currentSession.id,
        activePhase,
        {
          requirement: defaultRequirement || "三阶段大纲议事",
          use_topology_inference: useTopologyInference,
          target_words: targetWords,
          volume_count: volumeCount,
          chapters_per_volume: chaptersPerVolume,
          chapter_word_target: chapterWordTarget,
          chapter_word_min: chapterWordMin,
          chapter_word_max: chapterWordMax,
          scale_plan: scalePlan,
          target_volume_no: selectedVolumeNo,
          target_chapter_no: startChapter,
          chapter_ranges: [{ volume_no: selectedVolumeNo, start_chapter_no: startChapter, end_chapter_no: startChapter }],
          refresh_phase: refreshPhase,
          join_discussion: joinDiscussion,
          finish_phase: Boolean(options.finishPhase),
        },
	        (event) => {
	          finalEventType = event.type;
	          pushStreamEvent(event);
	          if (event.type === "pause") {
	            setSession(event.session);
          }
          if (event.type === "done") {
            setSession(event.session);
            onPhaseComplete?.(event.phase_run);
          }
        },
        controller.signal,
      );
      if (finalEventType === "pause") message.info("已暂停，等待你的意见或继续下一轮");
      if (finalEventType === "done") message.success(`${phaseLabels[activePhase]}完成`);
    } catch (error) {
      if ((error as Error).name !== "AbortError") message.error(error instanceof Error ? error.message : "大纲议事失败");
    } finally {
      setRunningPhase(null);
    }
  };

  const postUserMessage = async () => {
    const trimmed = userMessage.trim();
    if (!trimmed) {
      message.warning("先输入你想加入讨论的意见");
      return;
    }
    try {
      if (running) {
        abortRef.current?.abort();
        setRunningPhase(null);
      }
      const currentSession = await ensureSession();
      const result = await studioApi.postOutlineDebateMessage(projectId, currentSession.id, {
        phase: activePhase,
        message: trimmed,
        target_agent_name: detectTargetAgent(trimmed) || undefined,
      });
      setSession(result.session);
      appendUserMessageEvent(result.message, result.session);
      setUserMessage("");
      message.success(running ? "已打断当前接收，意见会在下一轮回应" : "意见已加入下一轮上下文");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "保存用户意见失败");
    }
  };

  const interruptDiscussion = async () => {
    abortRef.current?.abort();
    if (!session) {
      message.info("当前还没有运行中的议事会话");
      return;
    }
    try {
      const result = await studioApi.interruptOutlineDebateSession(projectId, session.id, {
        phase: activePhase,
        reason: "用户打断了当前议事。",
      });
      setSession(result.session);
      setEvents((current) => [
        ...current,
        { type: "interrupt", phase: activePhase, message: "用户打断了当前议事。", session: result.session },
      ]);
      message.warning("已打断当前议事");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "打断议事失败");
    } finally {
      setRunningPhase(null);
    }
  };

  const confirmActivePhase = async () => {
    if (!session || !activeRun) {
      message.warning("请先形成阶段结论，再确认条目");
      return;
    }
    try {
      const itemLabel = activePhase === "volumes" ? `第${selectedVolumeNo}卷` : activePhase === "chapters" ? `第${selectedChapterNo}章` : "";
      const result = await studioApi.confirmOutlineDebatePhase(projectId, session.id, activePhase, {
        item_key: activeItemKey || undefined,
        notes: `${confirmActionLabels[activePhase]}${itemLabel ? `（${itemLabel}）` : ""}：用户在议事面板确认，服务层写入正典。`,
      });
      setSession(result.session);
      if (activePhase === "book") {
        onFormalCommit?.();
      } else {
        const confirmedRun = result.session.phase_runs?.[activePhase];
        if (confirmedRun) onPhaseComplete?.(confirmedRun);
      }
      message.success(activePhase === "book" ? "总纲已确认并写入总纲正文" : `${itemLabel}已确认并更新正典`);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "确认条目失败");
    }
  };

  const commitConfirmedCandidates = async () => {
    if (!session || !allCandidatesConfirmed) {
      message.warning("请先确认总纲、卷纲和章纲条目");
      return;
    }
    try {
      const result = await studioApi.commitOutlineDebateCandidates(projectId, session.id, {
        overwrite_existing_chapters: true,
        notes: "用户在议事面板确认三阶段条目后写入正式大纲。",
      });
      setSession(result.session);
      onFormalCommit?.();
      message.success("已写入正式大纲");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "写入正式大纲失败");
    }
  };

  return (
    <section className={`outline-debate-panel ${compact ? "is-compact" : ""}`}>
      <div className="outline-debate-header">
        <div>
          <Space size={8}>
            <Radio size={16} />
          <Typography.Text strong>三阶段大纲议事引擎</Typography.Text>
          </Space>
          <div className="outline-debate-scale-summary">
            <Tag>总字数 {compactNumber(summaryTargetWords)}</Tag>
            <Tag>卷章 {compactNumber(summaryVolumeCount)}卷 / {compactNumber(summaryChapterCount)}章</Tag>
            <Tag>单章 {compactNumber(summaryChapterTarget)}字</Tag>
          </div>
        </div>
        <Space wrap>
          {phaseStatus(session, "book", phaseFullyConfirmed("book"))}
          {phaseStatus(session, "volumes", phaseFullyConfirmed("volumes"))}
          {phaseStatus(session, "chapters", phaseFullyConfirmed("chapters"))}
        </Space>
      </div>
      <div className="outline-debate-controls">
        <Segmented
          value={activePhase}
          onChange={(value) => {
            setActivePhase(value as OutlineDebatePhase);
            setUserPinnedToLatest(true);
          }}
          options={(Object.keys(phaseLabels) as OutlineDebatePhase[]).map((phase) => ({
            label: (
              <span className="outline-debate-phase-label">
                {phaseIcons[phase]}
                {phaseLabels[phase]}
              </span>
            ),
            value: phase,
          }))}
        />
        <Space wrap>
          <Space size={6}>
            <Switch checked={joinDiscussion} onChange={setJoinDiscussion} />
            <Typography.Text>加入讨论</Typography.Text>
          </Space>
          <Button type="primary" icon={<Play size={15} />} loading={running} disabled={confirmedRefreshBlocked} onClick={() => runActivePhase({ refreshPhase: true })}>
            流式讨论
          </Button>
          <Button icon={<RefreshCw size={15} />} disabled={running || confirmedRefreshBlocked} onClick={() => runActivePhase({ refreshPhase: true })}>
            刷新本阶段
          </Button>
          <Button icon={<CheckCircle2 size={15} />} disabled={!canConfirmActivePhase} onClick={confirmActivePhase}>
            {activePhase === "volumes" ? `确认本卷 ${selectedVolumeNo}` : activePhase === "chapters" ? `确认本章 ${selectedChapterNo}` : confirmActionLabels[activePhase]}
          </Button>
          <Button icon={<BookOpen size={15} />} disabled={running || !allCandidatesConfirmed || alreadyCommitted} onClick={commitConfirmedCandidates}>
            {alreadyCommitted ? "已写入正式大纲" : "写入正式大纲"}
          </Button>
          <Button icon={<PauseCircle size={15} />} danger disabled={!running && !session} onClick={interruptDiscussion}>
            打断发言
          </Button>
          <Button icon={<CheckCircle2 size={15} />} disabled={running || !session} onClick={() => runActivePhase({ refreshPhase: false, finishPhase: true })}>
            形成阶段结论
          </Button>
        </Space>
      </div>
      <div className="outline-debate-body">
        <div className="outline-debate-stream">
          <div className="outline-section-heading">
            <Typography.Text strong>真实 Agent 议事流</Typography.Text>
            <Space size={6} wrap>
              {currentSpeakerLabel ? <Tag color="processing">当前发言：{currentSpeakerLabel}</Tag> : null}
              <Tag color={activeCandidateStatus.color}>{activeCandidateStatus.text}</Tag>
              {!userPinnedToLatest && events.length ? (
                <Button className="outline-debate-scroll-back" size="small" icon={<ArrowDown size={13} />} onClick={scrollToLatest}>
                  回到最新发言
                </Button>
              ) : null}
              <Tag color={running ? "processing" : activeRun ? "green" : "default"}>{running ? "运行中" : activeRun ? "已保存" : "等待开始"}</Tag>
            </Space>
          </div>
          <div className="outline-debate-stream-body" ref={streamViewportRef} onScroll={handleStreamScroll}>
            {events.length ? (
              <Timeline
                items={events.map((event, index) => ({
                  key: `${event.type}-${index}`,
                  color: eventColor(event),
                  children: (
                    <>
                      {shouldShowRoundSeparator(events, index, event) && event.type === "turn" ? (
                        <div className="outline-debate-round-separator">第 {event.turn.round_no} 轮</div>
                      ) : null}
                      <div className={`outline-debate-event ${event.type === "turn" && event.turn.agent_name === currentSpeakerName ? "is-active-speaker" : ""}`}>
                        <Typography.Text strong>{eventTitle(event)}</Typography.Text>
	                        {event.type === "turn" ? (
	                          <div className="outline-debate-event-meta">
	                            <Tag>{agentDisplayName(event.turn.agent_name)}</Tag>
	                            <Typography.Text type="secondary">第 {event.turn.round_no} 轮发言</Typography.Text>
	                            {event.turn.handoff?.display ? <Tag color="blue">交接：{event.turn.handoff.display}</Tag> : null}
	                          </div>
	                        ) : null}
                        <Typography.Paragraph className="outline-debate-event-text" type="secondary">{eventDescription(event)}</Typography.Paragraph>
                      </div>
                    </>
                  ),
                }))}
              />
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="选择阶段后启动流式讨论" />
            )}
            <div className="outline-debate-stream-end" ref={streamEndRef} />
          </div>
        </div>
      </div>
      {joinDiscussion ? (
        <div className="outline-debate-composer-dock">
          <div className="outline-debate-composer">
            <Mentions
              value={userMessage}
              onChange={setUserMessage}
              rows={2}
              options={debateAgents.map((agent) => ({ value: agent.value, label: agent.label }))}
              placeholder="@结构医生 请先检查危机、高潮、结果有没有混淆"
            />
            <Space className="outline-debate-command-row" wrap>
              <Button icon={<MessageSquare size={15} />} disabled={!userMessage.trim()} onClick={postUserMessage}>
                发表意见
              </Button>
              <Button icon={<StepForward size={15} />} disabled={running || !session || (!paused && !hasPendingUserMessage)} onClick={() => runActivePhase({ refreshPhase: false })}>
                {hasPendingUserMessage ? "回应意见" : "继续下一轮"}
              </Button>
              {hasPendingUserMessage ? <Tag color="purple">有待回应意见</Tag> : null}
            </Space>
          </div>
        </div>
      ) : null}
    </section>
  );
}
