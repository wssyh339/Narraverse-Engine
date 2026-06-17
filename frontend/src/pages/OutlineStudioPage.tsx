import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, App } from "antd";
import { createRef, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { studioApi } from "../api/studio";
import type { Chapter, Volume } from "../types/api";
import { CanonStudioPanel } from "./outline/CanonStudioPanel";
import { CreateChapterForm, CreateVolumeForm, type ChapterCreateValues, type OutlineCreateFormHandle, type VolumeCreateValues } from "./outline/OutlineCreateForms";
import { OutlineDebatePanel } from "./outline/OutlineDebatePanel";
import { OutlineDirectory } from "./outline/OutlineDirectory";
import { OutlineEditorPanel } from "./outline/OutlineEditorPanel";
import type { OutlineView } from "./outline/types";
import { buildProjectScalePlan } from "./outline/outlineGeneration";
import { sameStringArray } from "./outline/outlineUtils";
import { useOutlineBulkSelection } from "./outline/useOutlineBulkSelection";
const EMPTY_CHAPTERS: Chapter[] = [];
export function OutlineStudioPage() {
  const { projectId = "" } = useParams();
  const queryClient = useQueryClient();
  const { message: messageApi, modal } = App.useApp();
  const volumesQuery = useQuery({ queryKey: ["volumes", projectId], queryFn: () => studioApi.listVolumes(projectId), enabled: !!projectId });
  const stateQuery = useQuery({ queryKey: ["state", projectId], queryFn: () => studioApi.getState(projectId), enabled: !!projectId });
  const [selectedView, setSelectedView] = useState<OutlineView>("outline");
  const [detailOpen, setDetailOpen] = useState(false);
  const [selectedVolumeId, setSelectedVolumeId] = useState("");
  const [selectedChapterId, setSelectedChapterId] = useState("");
  const [selectedChapterIds, setSelectedChapterIds] = useState<string[]>([]);
  const [selectedVolumeIds, setSelectedVolumeIds] = useState<string[]>([]);
  const [batchManagementEnabled, setBatchManagementEnabled] = useState(false);
  const [lastOutlinePlan, setLastOutlinePlan] = useState<Record<string, unknown> | null>(null);
  const useTopologyInference = true;

  const volumes = volumesQuery.data?.volumes ?? [];
  const projectState = stateQuery.data?.state;
  const chapters = projectState?.chapters ?? EMPTY_CHAPTERS;
  const project = projectState?.project;
  const storyBible = projectState?.story_bible;
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
      invalidate();
    },
    onError: (error) => messageApi.error(error instanceof Error ? error.message : "创建失败"),
  });
  const createChapter = useMutation({
    mutationFn: (values: { title: string; outline: string }) => studioApi.createChapter(projectId, { ...values, volume_no: selectedVolume?.volume_no ?? 1 }),
    onSuccess: () => {
      messageApi.success("章节与章纲已创建");
      invalidate();
    },
    onError: (error) => messageApi.error(error instanceof Error ? error.message : "创建失败"),
  });
  const trashOneChapter = useMutation({
    mutationFn: (chapterId: string) => studioApi.trashChapter(projectId, chapterId),
    onSuccess: (_, chapterId) => {
      messageApi.success("章节已删除");
      setSelectedChapterIds((current) => current.filter((id) => id !== chapterId));
      if (selectedChapterId === chapterId) {
        setSelectedChapterId("");
        setSelectedView("outline");
        setDetailOpen(false);
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
        setDetailOpen(false);
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
        setSelectedVolumeId(""); setSelectedChapterId(""); setSelectedView("outline"); setDetailOpen(false);
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
        setSelectedVolumeId(""); setSelectedChapterId(""); setSelectedView("outline"); setDetailOpen(false);
      }
      invalidate();
    },
    onError: (error) => messageApi.error(error instanceof Error ? error.message : "批量删除卷纲失败"),
  });
  const clearOutline = useMutation({
    mutationFn: () => studioApi.updateStoryBible(projectId, { world_setting: "", main_conflict: "", themes: [], style_guide: "" }),
    onSuccess: () => {
      setLastOutlinePlan(null);
      setSelectedView("outline");
      setDetailOpen(false);
      messageApi.success("总纲已删除");
      invalidate();
    },
    onError: (error) => messageApi.error(error instanceof Error ? error.message : "删除总纲失败"),
  });

  const openCreateVolume = () => {
    const formRef = createRef<OutlineCreateFormHandle<VolumeCreateValues>>();
    modal.confirm({
      title: "新建分卷",
      content: <CreateVolumeForm ref={formRef} />,
      onOk: () => formRef.current?.validate().then((values) => createVolume.mutateAsync(values)),
    });
  };

  const openCreateChapter = () => {
    const formRef = createRef<OutlineCreateFormHandle<ChapterCreateValues>>();
    modal.confirm({
      title: "新建章节与章纲",
      content: <CreateChapterForm ref={formRef} />,
      onOk: () => formRef.current?.validate().then((values) => createChapter.mutateAsync(values)),
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
      messageApi.warning("当前没有可删除的总纲");
      return;
    }
    confirmDanger("删除总纲", "确认删除当前页面中的总纲、推演链，并清空故事圣经中的世界观、核心冲突、主题和风格字段？此操作不会删除卷纲或章纲。", "删除总纲", clearOutline.isPending, () => clearOutline.mutateAsync());
  };

  if (volumesQuery.isLoading || stateQuery.isLoading) return <div className="outline-studio-grid"><div className="studio-panel loading-panel" /></div>;
  if (volumesQuery.error || stateQuery.error) return <Alert type="error" showIcon message="无法读取大纲数据" />;

  const openDetailView = (view: OutlineView) => {
    setSelectedView(view);
    setDetailOpen(true);
  };
  const directoryState = { batchManagementEnabled, selectedView, detailOpen, selectedVolumeId: selectedVolume?.id ?? "", selectedChapterId, selectedChapterIds, selectedChapterIdsAcrossDirectory, selectedVolumeIds, selectedVolumeIdsAcrossDirectory, allDirectorySelected, partialDirectorySelected, allVolumeOutlinesSelected, partialVolumeOutlinesSelected, isDeletingSelected: deleteSelectedChapters.isPending, isDeletingOne: trashOneChapter.isPending, isDeletingVolume: deleteVolume.isPending, isDeletingSelectedVolumes: deleteSelectedVolumes.isPending, hasGeneratedOutline: hasDeletableOutline };
  const directoryHandlers = { setSelectedView: openDetailView, setSelectedVolumeId, setSelectedChapterId, setDetailOpen, setBatchManagementEnabled, openCreateVolume, openCreateChapter, confirmClearOutline, confirmDeleteVolume, confirmBatchDeleteVolumes, toggleDirectorySelection, toggleVolumeSelection, toggleVolumeOutlineSelection, toggleAllVolumeOutlines, toggleChapterSelection, confirmTrashChapter, confirmBatchTrashChapters };
  const debateScalePlan = buildProjectScalePlan(project);
  const debatePanel = <OutlineDebatePanel projectId={projectId} defaultRequirement={[project?.premise, storyBible?.main_conflict, selectedVolume?.outline, selectedChapter?.outline].filter(Boolean).join("\n")} volumeCount={debateScalePlan.volume_count} chaptersPerVolume={debateScalePlan.chapters_per_volume} targetWords={debateScalePlan.target_words} chapterWordTarget={debateScalePlan.chapter_word_target} chapterWordMin={debateScalePlan.chapter_word_min} chapterWordMax={debateScalePlan.chapter_word_max} scalePlan={debateScalePlan} selectedVolumeNo={selectedVolume?.volume_no ?? 1} selectedChapterNo={selectedChapter?.chapter_no ?? 1} useTopologyInference={useTopologyInference} compact={detailOpen} onFormalCommit={() => { invalidate(); setSelectedView("outline"); setDetailOpen(true); }} />;

  return (
    <div className={`outline-studio-grid ${detailOpen ? "is-detail-open" : "is-debate-focus"}`}>
      <OutlineDirectory volumes={volumes} chapters={chapters} {...directoryState} handlers={directoryHandlers} />
      {detailOpen ? (
        <OutlineEditorPanel selectedView={selectedView} selectedVolume={selectedVolume} selectedChapter={selectedChapter} lastOutlinePlan={lastOutlinePlan} project={project} storyBible={storyBible ?? undefined}>
          <CanonStudioPanel projectId={projectId} project={project} storyBible={storyBible ?? undefined} />
        </OutlineEditorPanel>
      ) : null}
      {debatePanel}
    </div>
  );
}
