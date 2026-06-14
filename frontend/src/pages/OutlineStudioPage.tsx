import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, App, Form, Input } from "antd";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { studioApi } from "../api/studio";
import type { Chapter, Volume } from "../types/api";
import { CanonStudioPanel } from "./outline/CanonStudioPanel";
import { OutlineDirectory } from "./outline/OutlineDirectory";
import { formatOutlineDocument, OutlineEditorPanel } from "./outline/OutlineEditorPanel";
import { OutlineGenerationModal } from "./outline/OutlineGenerationModal";
import type { GenerationMode, InferenceStep, LongOutlineForm, OutlineTopology, OutlineView } from "./outline/types";
import { buildBookOutlineGenerateRequest, buildChapterOutlineBatchGenerateRequest, buildInitialOutlineValues, isOutlinePlanResultReady, mergeOutlinePlanResult } from "./outline/outlineGeneration";
import { buildRunningInferenceSteps, getProtagonist, resolveCurrentInferenceAgent, sameStringArray, summarizeProtagonist, updateInferenceStepsFromJob } from "./outline/outlineUtils";
import { useOutlineBulkSelection } from "./outline/useOutlineBulkSelection";
import { useOutlineGenerationJob } from "./outline/useOutlineGenerationJob";
const EMPTY_CHAPTERS: Chapter[] = [];
export function OutlineStudioPage() {
  const { projectId = "" } = useParams();
  const queryClient = useQueryClient();
  const { message: messageApi, modal } = App.useApp();
  const volumesQuery = useQuery({ queryKey: ["volumes", projectId], queryFn: () => studioApi.listVolumes(projectId), enabled: !!projectId });
  const stateQuery = useQuery({ queryKey: ["state", projectId], queryFn: () => studioApi.getState(projectId), enabled: !!projectId });
  const [selectedView, setSelectedView] = useState<OutlineView>("outline");
  const [selectedVolumeId, setSelectedVolumeId] = useState("");
  const [selectedChapterId, setSelectedChapterId] = useState("");
  const [selectedChapterIds, setSelectedChapterIds] = useState<string[]>([]);
  const [selectedVolumeIds, setSelectedVolumeIds] = useState<string[]>([]);
  const [batchManagementEnabled, setBatchManagementEnabled] = useState(false);
  const [outlinePreviewOpen, setOutlinePreviewOpen] = useState(false);
  const [generationMode, setGenerationMode] = useState<GenerationMode>("outline");
  const [pendingGenerationMode, setPendingGenerationMode] = useState<GenerationMode>("outline");
  const [useTopologyInference, setUseTopologyInference] = useState(true);
  const [generationStarted, setGenerationStarted] = useState(false);
  const [inferenceSteps, setInferenceSteps] = useState<InferenceStep[]>([]);
  const [activeAgentName, setActiveAgentName] = useState("");
  const [lastOutlinePlan, setLastOutlinePlan] = useState<Record<string, unknown> | null>(null);
  const [pendingOutlinePlan, setPendingOutlinePlan] = useState<Record<string, unknown> | null>(null);
  const [pendingOutlineJobId, setPendingOutlineJobId] = useState("");
  const [volumeForm] = Form.useForm<{ title: string; outline: string }>();
  const [chapterForm] = Form.useForm<{ title: string; outline: string }>();
  const [generationForm] = Form.useForm<LongOutlineForm>();
  const watchedVolumeCount = Form.useWatch("volume_count", generationForm);
  const watchedChaptersPerVolume = Form.useWatch("chapters_per_volume", generationForm);
  const watchedChapterWordTarget = Form.useWatch("chapter_word_target", generationForm);

  const volumes = volumesQuery.data?.volumes ?? [];
  const projectState = stateQuery.data?.state;
  const chapters = projectState?.chapters ?? EMPTY_CHAPTERS;
  const project = projectState?.project;
  const storyBible = projectState?.story_bible;
  const protagonist = getProtagonist(projectState?.characters ?? []);
  const selectedVolume = useMemo(() => volumes.find((item) => item.id === selectedVolumeId) ?? volumes[0], [selectedVolumeId, volumes]);
  const selectedChapter = useMemo(() => chapters.find((item) => item.id === selectedChapterId), [selectedChapterId, chapters]);
  const chaptersByVolumeNo = useMemo(() => {
    const grouped = new Map<number, Chapter[]>();
    chapters.forEach((chapter) => {
      const items = grouped.get(chapter.volume_no) ?? [];
      items.push(chapter);
      grouped.set(chapter.volume_no, items);
    });
    return grouped;
  }, [chapters]);
  const {
    selectedChapterIdsAcrossDirectory,
    deletableVolumeIds,
    selectedVolumeIdsAcrossDirectory,
    allDirectorySelected,
    partialDirectorySelected,
    allVolumeOutlinesSelected,
    partialVolumeOutlinesSelected,
  } = useOutlineBulkSelection({ volumes, chapters, selectedChapterIds, selectedVolumeIds, chaptersByVolumeNo });
  const hasStoryBibleOutline = Boolean(storyBible?.world_setting || storyBible?.main_conflict || storyBible?.themes?.length || storyBible?.style_guide);
  const hasDeletableOutline = Boolean(lastOutlinePlan || hasStoryBibleOutline);
  const computedTargetWords = Number(watchedVolumeCount || 0) * Number(watchedChaptersPerVolume || 0) * Number(watchedChapterWordTarget || 0);
  const generationResultText = useMemo(() => (pendingOutlinePlan ? formatOutlineDocument(pendingOutlinePlan, storyBible ?? undefined, project) : ""), [pendingOutlinePlan, project, storyBible]);
  const outlineTopology = useMemo(() => (pendingOutlinePlan?.outline_topology && typeof pendingOutlinePlan.outline_topology === "object" ? (pendingOutlinePlan.outline_topology as OutlineTopology) : null), [pendingOutlinePlan]);
  const isOutlineResultReady = isOutlinePlanResultReady(pendingOutlinePlan);

  useEffect(() => {
    if (outlinePreviewOpen && computedTargetWords > 0) generationForm.setFieldValue("target_words", computedTargetWords);
  }, [computedTargetWords, generationForm, outlinePreviewOpen]);
  useEffect(() => {
    setSelectedChapterIds((current) => {
      const next = current.filter((chapterId) => chapters.some((chapter) => chapter.id === chapterId));
      return sameStringArray(current, next) ? current : next;
    });
  }, [chapters]);
  useEffect(() => {
    if (!batchManagementEnabled) {
      setSelectedChapterIds((current) => (current.length ? [] : current));
      setSelectedVolumeIds((current) => (current.length ? [] : current));
    }
  }, [batchManagementEnabled]);
  useEffect(() => {
    setSelectedVolumeIds((current) => {
      const next = current.filter((volumeId) => deletableVolumeIds.includes(volumeId));
      return sameStringArray(current, next) ? current : next;
    });
  }, [deletableVolumeIds]);
  const invalidate = () => ["volumes", "state", "project-shell"].forEach((key) => queryClient.invalidateQueries({ queryKey: [key, projectId] }));
  const createVolume = useMutation({
    mutationFn: (values: { title: string; outline: string }) => studioApi.createVolume(projectId, values),
    onSuccess: () => {
      messageApi.success("分卷已创建");
      volumeForm.resetFields();
      invalidate();
    },
    onError: (error) => messageApi.error(error instanceof Error ? error.message : "创建失败"),
  });
  const createChapter = useMutation({
    mutationFn: (values: { title: string; outline: string }) => studioApi.createChapter(projectId, { ...values, volume_no: selectedVolume?.volume_no ?? 1 }),
    onSuccess: () => {
      messageApi.success("章节与章纲已创建");
      chapterForm.resetFields();
      invalidate();
    },
    onError: (error) => messageApi.error(error instanceof Error ? error.message : "创建失败"),
  });
  const saveVolume = useMutation({
    mutationFn: (values: { title: string; outline: string }) => studioApi.updateVolume(projectId, selectedVolume!.id, values),
    onSuccess: () => {
      messageApi.success("卷纲已保存");
      invalidate();
    },
  });
  const saveChapter = useMutation({
    mutationFn: (values: Partial<Chapter>) => studioApi.updateChapter(projectId, selectedChapter!.id, values),
    onSuccess: () => {
      messageApi.success("章纲已保存");
      invalidate();
    },
  });
  const trashOneChapter = useMutation({
    mutationFn: (chapterId: string) => studioApi.trashChapter(projectId, chapterId),
    onSuccess: (_, chapterId) => {
      messageApi.success("章节已删除");
      setSelectedChapterIds((current) => current.filter((id) => id !== chapterId));
      if (selectedChapterId === chapterId) {
        setSelectedChapterId("");
        setSelectedView("outline");
      }
      invalidate();
    },
    onError: (error) => messageApi.error(error instanceof Error ? error.message : "删除失败"),
  });
  const deleteSelectedChapters = useMutation({
    mutationFn: (chapterIds: string[]) => studioApi.trashChapters(projectId, chapterIds),
    onSuccess: (_, chapterIds) => {
      messageApi.success(`已删除 ${chapterIds.length} 个章纲`);
      setSelectedChapterIds([]);
      if (selectedChapterId && chapterIds.includes(selectedChapterId)) {
        setSelectedChapterId("");
        setSelectedView("outline");
      }
      invalidate();
    },
    onError: (error) => messageApi.error(error instanceof Error ? error.message : "批量删除失败"),
  });
  const deleteVolume = useMutation({
    mutationFn: (volumeId: string) => studioApi.deleteVolume(projectId, volumeId),
    onSuccess: (_, volumeId) => {
      messageApi.success("卷纲已删除");
      setSelectedVolumeIds((current) => current.filter((id) => id !== volumeId));
      if (selectedVolumeId === volumeId || selectedVolume?.id === volumeId) {
        setSelectedVolumeId(""); setSelectedChapterId(""); setSelectedView("outline");
      }
      invalidate();
    },
    onError: (error) => messageApi.error(error instanceof Error ? error.message : "删除卷纲失败"),
  });
  const deleteSelectedVolumes = useMutation({
    mutationFn: (volumeIds: string[]) => Promise.all(volumeIds.map((volumeId) => studioApi.deleteVolume(projectId, volumeId))),
    onSuccess: (_, volumeIds) => {
      messageApi.success(`已删除 ${volumeIds.length} 个卷纲`);
      setSelectedVolumeIds([]);
      if (selectedVolumeId && volumeIds.includes(selectedVolumeId)) {
        setSelectedVolumeId(""); setSelectedChapterId(""); setSelectedView("outline");
      }
      invalidate();
    },
    onError: (error) => messageApi.error(error instanceof Error ? error.message : "批量删除卷纲失败"),
  });
  const clearOutline = useMutation({
    mutationFn: () => studioApi.updateStoryBible(projectId, { world_setting: "", main_conflict: "", themes: [], style_guide: "" }),
    onSuccess: () => {
      setLastOutlinePlan(null);
      setPendingOutlinePlan(null);
      setInferenceSteps([]);
      setSelectedView("outline");
      messageApi.success("总纲已删除");
      invalidate();
    },
    onError: (error) => messageApi.error(error instanceof Error ? error.message : "删除总纲失败"),
  });
  const plan = useMutation({
    mutationFn: ({ mode, values, outlineContext }: { mode: GenerationMode; values: LongOutlineForm; outlineContext?: Record<string, unknown> | null }) => {
      const selectedChaptersForBatch = selectedChapterIdsAcrossDirectory.map((chapterId) => chapters.find((chapter) => chapter.id === chapterId)).filter((chapter): chapter is Chapter => Boolean(chapter));
      const input = { mode, values, projectId, selectedVolume, selectedChapter, selectedChapters: selectedChaptersForBatch, outlineContext };
      return mode === "outline" ? studioApi.bookOutlineGenerate(projectId, buildBookOutlineGenerateRequest(input)) : studioApi.chapterOutlineBatchGenerate(projectId, buildChapterOutlineBatchGenerateRequest(input));
    },
  });
  const commitOutline = useMutation<unknown, Error, { mode: GenerationMode; jobId: string; outlinePlan: Record<string, unknown> | null }>({
    mutationFn: ({ mode, jobId, outlinePlan }: { mode: GenerationMode; jobId: string; outlinePlan: Record<string, unknown> | null }) =>
      mode === "outline"
        ? studioApi.bookOutlineCommit(projectId, jobId ? { job_id: jobId } : { outline_plan: outlinePlan ?? {} })
        : studioApi.chapterOutlineCommit(projectId, jobId ? { job_id: jobId } : { chapter_outlines: ((outlinePlan?.chapter_outlines as Record<string, unknown>[] | undefined) ?? []), overwrite_existing: true }),
    onSuccess: (_, variables) => {
      messageApi.success(variables.mode === "outline" ? "总纲和卷纲已确认更新" : "章纲已确认写入");
      setPendingOutlinePlan(null);
      setPendingOutlineJobId("");
      setGenerationStarted(false);
      setInferenceSteps([]);
      setActiveAgentName("");
      setOutlinePreviewOpen(false);
      invalidate();
    },
    onError: (error) => messageApi.error(error instanceof Error ? error.message : "确认更新失败"),
  });
  const handleOutlineComplete = (outlinePlan: Record<string, unknown> | null, job?: { id?: string }) => {
    const hasOutlineSwarm = Boolean(outlinePlan?.["outline_swarm"]);
    const topologyMode = outlinePlan?.outline_topology && typeof outlinePlan.outline_topology === "object" ? (outlinePlan.outline_topology as { mode?: unknown }).mode : undefined;
    const fallbackSteps = buildRunningInferenceSteps({ generationMode, useTopologyInference: topologyMode === "topology" || hasOutlineSwarm });
    const runningSteps = inferenceSteps.length || hasOutlineSwarm ? inferenceSteps : fallbackSteps;
    const completedSteps = (runningSteps.length ? runningSteps : fallbackSteps).map((step) => ({ ...step, output_key: step.output_key === "等待上游 Agent 交接" ? "已完成" : step.output_key, status: "succeeded" as const }));
    setPendingGenerationMode(generationMode);
    setPendingOutlinePlan(outlinePlan);
    setPendingOutlineJobId(job?.id ?? "");
    setLastOutlinePlan((current) => mergeOutlinePlanResult(current, generationMode, outlinePlan));
    setInferenceSteps(completedSteps);
    setActiveAgentName(completedSteps.at(-1)?.agent_name ?? "");
    setSelectedView("outline");
    invalidate();
  };
  const { isOutlineGenerating, startOutlineJob, clearOutlineJob } = useOutlineGenerationJob({ generationMode, useTopologyInference, planIsPending: plan.isPending, messageApi, setInferenceSteps, setActiveAgentName, onComplete: handleOutlineComplete });

  const buildInitialValues = (mode: GenerationMode): LongOutlineForm => buildInitialOutlineValues({ mode, project, storyBible: storyBible ?? undefined, protagonistSummary: summarizeProtagonist(protagonist), selectedVolume });

  const openGenerationPreview = (mode: GenerationMode) => {
    setGenerationMode(mode);
    setGenerationStarted(false); setPendingOutlinePlan(null); setPendingOutlineJobId(""); setActiveAgentName(""); setUseTopologyInference(true);
    generationForm.setFieldsValue(buildInitialValues(mode));
    setOutlinePreviewOpen(true);
  };

  const confirmGenerate = async () => {
    const values = await generationForm.validateFields();
    const runningSteps = buildRunningInferenceSteps({ generationMode, useTopologyInference: Boolean(values.use_topology_inference) });
    setUseTopologyInference(Boolean(values.use_topology_inference));
    setSelectedView("outline");
    setGenerationStarted(true);
    setPendingOutlinePlan(null);
    setInferenceSteps(runningSteps);
    setActiveAgentName(runningSteps[0]?.agent_name ?? "");
    try {
      const result = await plan.mutateAsync({ mode: generationMode, values, outlineContext: null });
      const job = result.job;
      const completedSteps = Number(job.progress?.completed_steps ?? 0);
      const currentAgent = job.current_agent || job.progress?.current_step || "";
      setActiveAgentName(resolveCurrentInferenceAgent(runningSteps, currentAgent, completedSteps));
      setInferenceSteps(updateInferenceStepsFromJob(runningSteps, currentAgent, completedSteps));
      if (job.status === "succeeded") {
        handleOutlineComplete(result.outline_plan ?? null, job);
        messageApi.success(generationMode === "outline" ? "大纲推演完成，请确认后写入" : "章纲推演完成，请确认后写入");
      } else {
        if (result.outline_plan?.outline_topology) setPendingOutlinePlan(result.outline_plan);
        startOutlineJob(job.id);
        messageApi.info("推演已进入后台任务，正在持续更新 Agent 进度");
      }
    } catch (error) {
      setInferenceSteps((steps) => steps.map((step) => (step.status === "running" ? { ...step, status: "failed" } : step)));
      clearOutlineJob();
      messageApi.error(error instanceof Error ? error.message : "生成失败");
    }
  };

  const confirmApplyOutlineUpdate = () => {
    if (!pendingOutlinePlan || !isOutlineResultReady) {
      messageApi.warning("请先完成一次推演");
      return;
    }
    setSelectedView(pendingGenerationMode === "outline" ? "outline" : "chapterOutline");
    commitOutline.mutate({ mode: pendingGenerationMode, jobId: pendingOutlineJobId, outlinePlan: pendingOutlinePlan });
  };

  const openCreateVolume = () => {
    modal.confirm({
      title: "新建分卷",
      content: (
        <Form form={volumeForm} layout="vertical">
          <Form.Item name="title" label="分卷名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="outline" label="卷纲"><Input.TextArea rows={4} /></Form.Item>
        </Form>
      ),
      onOk: () => volumeForm.validateFields().then((values) => createVolume.mutateAsync(values)),
    });
  };

  const openCreateChapter = () => {
    modal.confirm({
      title: "新建章节与章纲",
      content: (
        <Form form={chapterForm} layout="vertical">
          <Form.Item name="title" label="章节标题" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="outline" label="章纲"><Input.TextArea rows={4} /></Form.Item>
        </Form>
      ),
      onOk: () => chapterForm.validateFields().then((values) => createChapter.mutateAsync(values)),
    });
  };
  const confirmDanger = (title: string, content: string, okText: string, loading: boolean, onOk: () => Promise<unknown>, disabled = false) =>
    modal.confirm({ title, content, okText, cancelText: "取消", okButtonProps: { danger: true, disabled, loading }, onOk });

  const toggleChapterSelection = (chapterId: string, checked: boolean) => {
    setSelectedChapterIds((current) => (checked ? Array.from(new Set([...current, chapterId])) : current.filter((id) => id !== chapterId)));
  };

  const toggleDirectorySelection = (checked: boolean) => {
    const allChapterIds = chapters.map((chapter) => chapter.id);
    setSelectedChapterIds((current) => (checked ? Array.from(new Set([...current, ...allChapterIds])) : current.filter((chapterId) => !allChapterIds.includes(chapterId))));
  };

  const toggleAllVolumeOutlines = (checked: boolean) => {
    setSelectedVolumeIds((current) => (checked ? Array.from(new Set([...current, ...deletableVolumeIds])) : current.filter((volumeId) => !deletableVolumeIds.includes(volumeId))));
  };

  const toggleVolumeSelection = (volumeNo: number, checked: boolean) => {
    const volumeChapterIds = (chaptersByVolumeNo.get(volumeNo) ?? []).map((chapter) => chapter.id);
    setSelectedChapterIds((current) => {
      const currentSet = new Set(current);
      volumeChapterIds.forEach((chapterId) => (checked ? currentSet.add(chapterId) : currentSet.delete(chapterId)));
      return Array.from(currentSet);
    });
  };

  const toggleVolumeOutlineSelection = (volumeId: string, checked: boolean) => {
    if (!deletableVolumeIds.includes(volumeId)) return;
    setSelectedVolumeIds((current) => (checked ? Array.from(new Set([...current, volumeId])) : current.filter((id) => id !== volumeId)));
  };

  const confirmTrashChapter = (chapter: Chapter) =>
    confirmDanger("删除章纲", `确认删除「${chapter.title}」？删除后该章节不会继续显示在大纲目录中。`, "删除", trashOneChapter.isPending, () => trashOneChapter.mutateAsync(chapter.id));

  const confirmBatchTrashChapters = () => {
    const chapterIds = selectedChapterIdsAcrossDirectory;
    if (!chapterIds.length) {
      messageApi.warning("请先勾选要删除的章节");
      return;
    }
    confirmDanger("批量删除章节", `确认删除大纲目录中选中的 ${chapterIds.length} 个章节与章纲？删除后不会继续显示在目录中。`, "批量删除", deleteSelectedChapters.isPending, () => deleteSelectedChapters.mutateAsync(chapterIds));
  };

  const confirmBatchDeleteVolumes = () => {
    const volumeIds = selectedVolumeIdsAcrossDirectory;
    if (!volumeIds.length) {
      messageApi.warning("请先勾选要删除的卷纲");
      return;
    }
    confirmDanger("批量删除卷纲", `确认删除选中的 ${volumeIds.length} 个空卷纲？包含章节的分卷已自动排除，请先删除或移动章节后再删除。`, "批量删除卷纲", deleteSelectedVolumes.isPending, () => deleteSelectedVolumes.mutateAsync(volumeIds));
  };

  const confirmDeleteVolume = (volume: Volume) => {
    const activeChapterCount = chaptersByVolumeNo.get(volume.volume_no)?.length ?? 0;
    const content = activeChapterCount ? `「${volume.title}」下仍有 ${activeChapterCount} 个章节。请先删除或移动这些章节，再删除卷纲。` : `确认删除「${volume.title}」？删除后该分卷不会继续显示在大纲目录中。`;
    confirmDanger("删除卷纲", content, "删除卷纲", deleteVolume.isPending, () => deleteVolume.mutateAsync(volume.id), activeChapterCount > 0);
  };

  const confirmClearOutline = () => {
    if (!hasDeletableOutline) {
      messageApi.warning("当前没有可删除的生成大纲");
      return;
    }
    confirmDanger("删除总纲", "确认删除当前页面中的总纲、推演链，并清空故事圣经中的世界观、核心冲突、主题和风格字段？此操作不会删除卷纲或章纲。", "删除总纲", clearOutline.isPending, () => clearOutline.mutateAsync());
  };

  if (volumesQuery.isLoading || stateQuery.isLoading) return <div className="outline-studio-grid"><div className="studio-panel loading-panel" /></div>;
  if (volumesQuery.error || stateQuery.error) return <Alert type="error" showIcon message="无法读取大纲数据" />;

  const directoryState = { batchManagementEnabled, selectedView, selectedVolumeId: selectedVolume?.id ?? "", selectedChapterId, selectedChapterIds, selectedChapterIdsAcrossDirectory, selectedVolumeIds, selectedVolumeIdsAcrossDirectory, allDirectorySelected, partialDirectorySelected, allVolumeOutlinesSelected, partialVolumeOutlinesSelected, isDeletingSelected: deleteSelectedChapters.isPending, isDeletingOne: trashOneChapter.isPending, isDeletingVolume: deleteVolume.isPending, isDeletingSelectedVolumes: deleteSelectedVolumes.isPending, hasGeneratedOutline: hasDeletableOutline };
  const directoryHandlers = { setSelectedView, setSelectedVolumeId, setSelectedChapterId, setBatchManagementEnabled, openCreateVolume, openCreateChapter, openGenerationPreview, confirmClearOutline, confirmDeleteVolume, confirmBatchDeleteVolumes, toggleDirectorySelection, toggleVolumeSelection, toggleVolumeOutlineSelection, toggleAllVolumeOutlines, toggleChapterSelection, confirmTrashChapter, confirmBatchTrashChapters };

  return (
    <>
      <div className="outline-studio-grid">
        <OutlineDirectory volumes={volumes} chapters={chapters} {...directoryState} handlers={directoryHandlers} />
        <OutlineEditorPanel
          selectedView={selectedView}
          selectedVolume={selectedVolume}
          selectedChapter={selectedChapter}
          lastOutlinePlan={lastOutlinePlan}
          project={project}
          storyBible={storyBible ?? undefined}
          isPlanning={isOutlineGenerating}
          saveVolume={saveVolume}
          saveChapter={saveChapter}
          openGenerationPreview={openGenerationPreview}
        >
          <CanonStudioPanel projectId={projectId} project={project} storyBible={storyBible ?? undefined} />
        </OutlineEditorPanel>
      </div>
      <OutlineGenerationModal
        open={outlinePreviewOpen}
        generationMode={generationMode}
        generationStarted={generationStarted}
        form={generationForm}
        inferenceSteps={inferenceSteps}
        outlineTopology={outlineTopology}
        outlinePlan={pendingOutlinePlan}
        activeAgentName={activeAgentName}
        isPending={isOutlineGenerating || commitOutline.isPending}
        hasResult={isOutlineResultReady}
        resultText={generationResultText}
        onOk={confirmGenerate}
        onConfirmUpdate={confirmApplyOutlineUpdate}
        onCancel={() => {
          setOutlinePreviewOpen(false);
          setGenerationStarted(false);
          setInferenceSteps([]);
          setActiveAgentName("");
        }}
      />
    </>
  );
}
