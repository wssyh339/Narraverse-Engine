import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, App, Form, Input } from "antd";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { studioApi } from "../api/studio";
import type { Chapter, Volume } from "../types/api";
import { CanonStudioPanel } from "./outline/CanonStudioPanel";
import { OutlineDirectory } from "./outline/OutlineDirectory";
import { OutlineEditorPanel } from "./outline/OutlineEditorPanel";
import { OutlineGenerationModal } from "./outline/OutlineGenerationModal";
import type { GenerationMode, InferenceStep, LongOutlineForm, OutlineView } from "./outline/types";
import { buildInitialOutlineValues, buildOutlinePlanRequest, mergeOutlinePlanResult } from "./outline/outlineGeneration";
import { buildSwarmInferenceSteps, getProtagonist, sameStringArray, summarizeProtagonist } from "./outline/outlineUtils";
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
  const [batchManagementEnabled, setBatchManagementEnabled] = useState(false);
  const [outlinePreviewOpen, setOutlinePreviewOpen] = useState(false);
  const [generationMode, setGenerationMode] = useState<GenerationMode>("outline");
  const [generationStarted, setGenerationStarted] = useState(false);
  const [inferenceSteps, setInferenceSteps] = useState<InferenceStep[]>([]);
  const [lastOutlinePlan, setLastOutlinePlan] = useState<Record<string, unknown> | null>(null);
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
  const selectedChapterIdsAcrossDirectory = useMemo(
    () => selectedChapterIds.filter((chapterId) => chapters.some((chapter) => chapter.id === chapterId)),
    [chapters, selectedChapterIds],
  );
  const allDirectorySelected = chapters.length > 0 && selectedChapterIdsAcrossDirectory.length === chapters.length;
  const partialDirectorySelected = selectedChapterIdsAcrossDirectory.length > 0 && !allDirectorySelected;
  const computedTargetWords = Number(watchedVolumeCount || 0) * Number(watchedChaptersPerVolume || 0) * Number(watchedChapterWordTarget || 0);

  useEffect(() => {
    if (outlinePreviewOpen && computedTargetWords > 0) {
      generationForm.setFieldValue("target_words", computedTargetWords);
    }
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
    }
  }, [batchManagementEnabled]);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["volumes", projectId] });
    queryClient.invalidateQueries({ queryKey: ["state", projectId] });
    queryClient.invalidateQueries({ queryKey: ["project-shell", projectId] });
  };

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
      if (selectedVolumeId === volumeId || selectedVolume?.id === volumeId) {
        setSelectedVolumeId("");
        setSelectedChapterId("");
        setSelectedView("outline");
      }
      invalidate();
    },
    onError: (error) => messageApi.error(error instanceof Error ? error.message : "删除卷纲失败"),
  });
  const plan = useMutation({
    mutationFn: ({ mode, values, outlineContext }: { mode: GenerationMode; values: LongOutlineForm; outlineContext?: Record<string, unknown> | null }) =>
      studioApi.planChapters(projectId, buildOutlinePlanRequest({ mode, values, projectId, selectedVolume, selectedChapter, outlineContext })),
  });

  const buildInitialValues = (mode: GenerationMode): LongOutlineForm => {
    return buildInitialOutlineValues({ mode, project, storyBible: storyBible ?? undefined, protagonistSummary: summarizeProtagonist(protagonist), selectedVolume });
  };

  const openGenerationPreview = (mode: GenerationMode) => {
    setGenerationMode(mode);
    setGenerationStarted(false);
    generationForm.setFieldsValue(buildInitialValues(mode));
    setOutlinePreviewOpen(true);
  };

  const confirmGenerate = async () => {
    const values = await generationForm.validateFields();
    setSelectedView("outline");
    setGenerationStarted(true);
    setLastOutlinePlan(null);
    setInferenceSteps([]);
    try {
      const result = await plan.mutateAsync({ mode: generationMode, values, outlineContext: null });
      const outlinePlan = result.outline_plan ?? null;
      const swarmSteps = buildSwarmInferenceSteps(outlinePlan?.["outline_swarm"]);
      setLastOutlinePlan(outlinePlan);
      setInferenceSteps(swarmSteps);
      messageApi.success(generationMode === "outline" ? "大纲推演完成" : generationMode === "volume" ? "卷纲推演完成" : "章纲推演完成");
      invalidate();
    } catch (error) {
      setInferenceSteps((steps) => steps.map((step) => (step.status === "running" ? { ...step, status: "failed" } : step)));
      messageApi.error(error instanceof Error ? error.message : "生成失败");
    }
  };

  const generateFromExistingOutline = async (mode: Extract<GenerationMode, "volume" | "chapter">) => {
    if (!lastOutlinePlan) {
      messageApi.warning("请先生成总纲，再继续生成卷纲或章纲");
      return;
    }
    setGenerationMode(mode);
    setGenerationStarted(true);
    setInferenceSteps([]);
    try {
      const result = await plan.mutateAsync({ mode, values: buildInitialValues(mode), outlineContext: lastOutlinePlan });
      const outlinePlan = result.outline_plan ?? null;
      setLastOutlinePlan((current) => mergeOutlinePlanResult(current, mode, outlinePlan));
      setInferenceSteps(buildSwarmInferenceSteps(outlinePlan?.["outline_swarm"]));
      messageApi.success(mode === "volume" ? "卷纲推演完成" : "章纲推演完成");
      invalidate();
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "生成失败");
    }
  };

  const openCreateVolume = () => {
    modal.confirm({
      title: "新建分卷",
      content: (
        <Form form={volumeForm} layout="vertical">
          <Form.Item name="title" label="分卷名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="outline" label="卷纲">
            <Input.TextArea rows={4} />
          </Form.Item>
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
          <Form.Item name="title" label="章节标题" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="outline" label="章纲">
            <Input.TextArea rows={4} />
          </Form.Item>
        </Form>
      ),
      onOk: () => chapterForm.validateFields().then((values) => createChapter.mutateAsync(values)),
    });
  };

  const toggleChapterSelection = (chapterId: string, checked: boolean) => {
    setSelectedChapterIds((current) => (checked ? Array.from(new Set([...current, chapterId])) : current.filter((id) => id !== chapterId)));
  };

  const toggleDirectorySelection = (checked: boolean) => {
    const allChapterIds = chapters.map((chapter) => chapter.id);
    setSelectedChapterIds((current) => (checked ? Array.from(new Set([...current, ...allChapterIds])) : current.filter((chapterId) => !allChapterIds.includes(chapterId))));
  };

  const toggleVolumeSelection = (volumeNo: number, checked: boolean) => {
    const volumeChapterIds = (chaptersByVolumeNo.get(volumeNo) ?? []).map((chapter) => chapter.id);
    setSelectedChapterIds((current) => {
      const currentSet = new Set(current);
      volumeChapterIds.forEach((chapterId) => (checked ? currentSet.add(chapterId) : currentSet.delete(chapterId)));
      return Array.from(currentSet);
    });
  };

  const confirmTrashChapter = (chapter: Chapter) => {
    modal.confirm({
      title: "删除章纲",
      content: `确认删除「${chapter.title}」？删除后该章节不会继续显示在大纲目录中。`,
      okText: "删除",
      cancelText: "取消",
      okButtonProps: { danger: true, loading: trashOneChapter.isPending },
      onOk: () => trashOneChapter.mutateAsync(chapter.id),
    });
  };

  const confirmBatchTrashChapters = () => {
    const chapterIds = selectedChapterIdsAcrossDirectory;
    if (!chapterIds.length) {
      messageApi.warning("请先勾选要删除的章节");
      return;
    }
    modal.confirm({
      title: "批量删除章节",
      content: `确认删除大纲目录中选中的 ${chapterIds.length} 个章节与章纲？删除后不会继续显示在目录中。`,
      okText: "批量删除",
      cancelText: "取消",
      okButtonProps: { danger: true, loading: deleteSelectedChapters.isPending },
      onOk: () => deleteSelectedChapters.mutateAsync(chapterIds),
    });
  };

  const confirmDeleteVolume = (volume: Volume) => {
    const activeChapterCount = chaptersByVolumeNo.get(volume.volume_no)?.length ?? 0;
    modal.confirm({
      title: "删除卷纲",
      content: activeChapterCount
        ? `「${volume.title}」下仍有 ${activeChapterCount} 个章节。请先删除或移动这些章节，再删除卷纲。`
        : `确认删除「${volume.title}」？删除后该分卷不会继续显示在大纲目录中。`,
      okText: "删除卷纲",
      cancelText: "取消",
      okButtonProps: { danger: true, disabled: activeChapterCount > 0, loading: deleteVolume.isPending },
      onOk: () => deleteVolume.mutateAsync(volume.id),
    });
  };

  const confirmClearOutline = () => {
    if (!lastOutlinePlan) {
      messageApi.warning("当前没有可删除的生成大纲");
      return;
    }
    modal.confirm({
      title: "删除总纲",
      content: "确认删除当前页面中的总纲和推演链？此操作不会清空故事圣经、卷纲或章纲。",
      okText: "删除总纲",
      cancelText: "取消",
      okButtonProps: { danger: true },
      onOk: () => {
        setLastOutlinePlan(null);
        setInferenceSteps([]);
        setSelectedView("outline");
        messageApi.success("总纲已删除");
      },
    });
  };

  if (volumesQuery.isLoading || stateQuery.isLoading) return <div className="outline-studio-grid"><div className="studio-panel loading-panel" /></div>;
  if (volumesQuery.error || stateQuery.error) return <Alert type="error" showIcon message="无法读取大纲数据" />;

  return (
    <>
      <div className="outline-studio-grid">
        <OutlineDirectory
          volumes={volumes}
          chapters={chapters}
          batchManagementEnabled={batchManagementEnabled}
          selectedView={selectedView}
          selectedVolumeId={selectedVolume?.id ?? ""}
          selectedChapterId={selectedChapterId}
          selectedChapterIds={selectedChapterIds}
          selectedChapterIdsAcrossDirectory={selectedChapterIdsAcrossDirectory}
          allDirectorySelected={allDirectorySelected}
          partialDirectorySelected={partialDirectorySelected}
          isDeletingSelected={deleteSelectedChapters.isPending}
          isDeletingOne={trashOneChapter.isPending}
          isDeletingVolume={deleteVolume.isPending}
          hasGeneratedOutline={Boolean(lastOutlinePlan)}
          handlers={{
            setSelectedView,
            setSelectedVolumeId,
            setSelectedChapterId,
            setBatchManagementEnabled,
            openCreateVolume,
            openCreateChapter,
            openGenerationPreview,
            confirmClearOutline,
            confirmDeleteVolume,
            toggleDirectorySelection,
            toggleVolumeSelection,
            toggleChapterSelection,
            confirmTrashChapter,
            confirmBatchTrashChapters,
          }}
        />
        <OutlineEditorPanel
          selectedView={selectedView}
          selectedVolume={selectedVolume}
          selectedChapter={selectedChapter}
          lastOutlinePlan={lastOutlinePlan}
          project={project}
          storyBible={storyBible ?? undefined}
          isPlanning={plan.isPending}
          saveVolume={saveVolume}
          saveChapter={saveChapter}
          openGenerationPreview={openGenerationPreview}
          generateFromExistingOutline={generateFromExistingOutline}
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
        isPending={plan.isPending}
        hasResult={Boolean(lastOutlinePlan)}
        onOk={confirmGenerate}
        onCancel={() => setOutlinePreviewOpen(false)}
      />
    </>
  );
}
