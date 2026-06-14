import { Button, Checkbox, Space, Switch, Tooltip, Typography } from "antd";
import { FilePlus2, FileText, FolderPlus, Layers, Plus, ScrollText, Trash2 } from "lucide-react";
import type { Chapter, Volume } from "../../types/api";
import type { OutlineDirectoryHandlers, OutlineView } from "./types";

interface OutlineDirectoryProps {
  volumes: Volume[];
  chapters: Chapter[];
  batchManagementEnabled: boolean;
  selectedView: OutlineView;
  selectedVolumeId: string;
  selectedChapterId: string;
  selectedChapterIds: string[];
  selectedChapterIdsAcrossDirectory: string[];
  selectedVolumeIds: string[];
  selectedVolumeIdsAcrossDirectory: string[];
  allDirectorySelected: boolean;
  partialDirectorySelected: boolean;
  allVolumeOutlinesSelected: boolean;
  partialVolumeOutlinesSelected: boolean;
  isDeletingSelected: boolean;
  isDeletingOne: boolean;
  isDeletingVolume: boolean;
  isDeletingSelectedVolumes: boolean;
  hasGeneratedOutline: boolean;
  handlers: OutlineDirectoryHandlers;
}

export function OutlineDirectory({
  volumes,
  chapters,
  batchManagementEnabled,
  selectedView,
  selectedVolumeId,
  selectedChapterId,
  selectedChapterIds,
  selectedChapterIdsAcrossDirectory,
  selectedVolumeIds,
  selectedVolumeIdsAcrossDirectory,
  allDirectorySelected,
  partialDirectorySelected,
  allVolumeOutlinesSelected,
  partialVolumeOutlinesSelected,
  isDeletingSelected,
  isDeletingOne,
  isDeletingVolume,
  isDeletingSelectedVolumes,
  hasGeneratedOutline,
  handlers,
}: OutlineDirectoryProps) {
  const selectedChapterIdSet = new Set(selectedChapterIds);
  const selectedVolumeIdSet = new Set(selectedVolumeIds);
  const chaptersByVolumeNo = new Map<number, Chapter[]>();
  chapters.forEach((chapter) => {
    const items = chaptersByVolumeNo.get(chapter.volume_no) ?? [];
    items.push(chapter);
    chaptersByVolumeNo.set(chapter.volume_no, items);
  });

  const renderVolumeChapterTree = () => (
    <section className="outline-directory-section">
      <div className="outline-section-label"><Layers size={15} />卷纲 / 章节目录</div>
      {volumes.map((volume) => {
        const volumeChapters = chaptersByVolumeNo.get(volume.volume_no) ?? [];
        const selectedInVolume = volumeChapters.filter((chapter) => selectedChapterIdSet.has(chapter.id));
        const allVolumeSelected = volumeChapters.length > 0 && selectedInVolume.length === volumeChapters.length;
        const partialVolumeSelected = selectedInVolume.length > 0 && !allVolumeSelected;
        return (
          <div key={volume.id} className="outline-volume-group">
            <div className={`outline-tree-row is-volume ${batchManagementEnabled ? "is-manage" : ""}`}>
              {batchManagementEnabled ? (
                <Checkbox
                  aria-label="选择卷纲"
                  checked={selectedVolumeIdSet.has(volume.id)}
                  disabled={Boolean(volumeChapters.length) || isDeletingSelectedVolumes || isDeletingVolume}
                  onClick={(event) => event.stopPropagation()}
                  onChange={(event) => handlers.toggleVolumeOutlineSelection(volume.id, event.target.checked)}
                />
              ) : null}
              <button
                className={`outline-tree-item ${selectedView === "volume" && volume.id === selectedVolumeId ? "is-active" : ""}`}
                onClick={() => {
                  handlers.setSelectedVolumeId(volume.id);
                  handlers.setSelectedChapterId("");
                  handlers.setSelectedView("volume");
                }}
              >
                <span className="outline-volume-index">{volume.volume_no}</span>
                <span>{volume.title}</span>
                <small>{volumeChapters.length}章</small>
              </button>
              {batchManagementEnabled ? (
                <Tooltip title={volumeChapters.length ? "该卷仍有章节，需先删除或移动章节" : "删除卷纲"}>
                  <Button
                    type="text"
                    danger
                    size="small"
                    aria-label="删除卷纲"
                    icon={<Trash2 size={14} />}
                    disabled={Boolean(volumeChapters.length)}
                    loading={isDeletingVolume}
                    onClick={() => handlers.confirmDeleteVolume(volume)}
                  />
                </Tooltip>
              ) : null}
            </div>
            {batchManagementEnabled ? (
              <div className="outline-volume-child-tools">
                <Checkbox
                  checked={allVolumeSelected}
                  indeterminate={partialVolumeSelected}
                  disabled={!volumeChapters.length || isDeletingSelected}
                  onChange={(event) => handlers.toggleVolumeSelection(volume.volume_no, event.target.checked)}
                >
                  全选本卷
                </Checkbox>
                <Typography.Text type="secondary">{selectedInVolume.length}/{volumeChapters.length}</Typography.Text>
              </div>
            ) : null}
            <div className="outline-nested-chapters">
              {volumeChapters.length ? (
                volumeChapters.map((chapter) => (
                  <div key={`${chapter.id}-nested`} className={`outline-tree-row ${batchManagementEnabled ? "is-batch" : ""}`}>
                    {batchManagementEnabled ? (
                      <Checkbox
                        checked={selectedChapterIdSet.has(chapter.id)}
                        disabled={isDeletingOne || isDeletingSelected}
                        onClick={(event) => event.stopPropagation()}
                        onChange={(event) => handlers.toggleChapterSelection(chapter.id, event.target.checked)}
                      />
                    ) : null}
                    <button
                      className={`outline-tree-item is-compact is-nested ${selectedChapterId === chapter.id && selectedView === "chapterOutline" ? "is-active" : ""}`}
                      onClick={() => {
                        handlers.setSelectedVolumeId(volume.id);
                        handlers.setSelectedChapterId(chapter.id);
                        handlers.setSelectedView("chapterOutline");
                      }}
                    >
                      <span>{chapter.chapter_no}</span>
                      <span>{chapter.title}</span>
                      <small>{chapter.plot_purpose || "章纲"}</small>
                    </button>
                    {batchManagementEnabled ? (
                      <Tooltip title="删除章节">
                        <Button
                          type="text"
                          danger
                          size="small"
                          aria-label="删除章节"
                          icon={<Trash2 size={14} />}
                          loading={isDeletingOne}
                          onClick={() => handlers.confirmTrashChapter(chapter)}
                        />
                      </Tooltip>
                    ) : null}
                  </div>
                ))
              ) : (
                <Typography.Text type="secondary" className="outline-empty-volume">暂无章节</Typography.Text>
              )}
            </div>
          </div>
        );
      })}
    </section>
  );

  return (
    <aside className="studio-panel outline-tree-panel">
      <div className="outline-directory-title">
        <div>
          <span className="outline-title-accent" />
          <Typography.Title level={4}>大纲目录</Typography.Title>
        </div>
        <Space size={6}>
          <Tooltip title="新建分卷"><Button type="text" icon={<FolderPlus size={16} />} onClick={handlers.openCreateVolume} /></Tooltip>
          <Tooltip title="新建章节"><Button type="text" icon={<FilePlus2 size={16} />} disabled={!volumes.length} onClick={handlers.openCreateChapter} /></Tooltip>
          <Tooltip title="添加"><Button type="primary" icon={<Plus size={17} />} onClick={() => handlers.openGenerationPreview("outline")} /></Tooltip>
        </Space>
      </div>
      <div className="outline-batch-toggle">
        <Space size={8}>
          <Typography.Text strong>批量管理</Typography.Text>
          <Typography.Text type="secondary">
            {batchManagementEnabled ? `已选择 ${selectedChapterIdsAcrossDirectory.length} 章 / ${selectedVolumeIdsAcrossDirectory.length} 卷` : "关闭后隐藏勾选框"}
          </Typography.Text>
        </Space>
        <Switch checked={batchManagementEnabled} onChange={handlers.setBatchManagementEnabled} />
      </div>
      {batchManagementEnabled ? (
        <div className="outline-directory-bulk-actions">
          <div className="outline-bulk-row">
            <Checkbox
              checked={allDirectorySelected}
              indeterminate={partialDirectorySelected}
              disabled={!chapters.length || isDeletingSelected}
              onChange={(event) => handlers.toggleDirectorySelection(event.target.checked)}
            >
              全选全部章节
            </Checkbox>
            <Button
              size="small"
              danger
              icon={<Trash2 size={14} />}
              disabled={!selectedChapterIdsAcrossDirectory.length}
              loading={isDeletingSelected}
              onClick={handlers.confirmBatchTrashChapters}
            >
              批量删除选中
            </Button>
          </div>
          <div className="outline-bulk-row">
            <Checkbox
              checked={allVolumeOutlinesSelected}
              indeterminate={partialVolumeOutlinesSelected}
              disabled={!volumes.length || isDeletingSelectedVolumes}
              onChange={(event) => handlers.toggleAllVolumeOutlines(event.target.checked)}
            >
              全选可删除卷纲
            </Checkbox>
            <Button
              size="small"
              danger
              icon={<Trash2 size={14} />}
              disabled={!selectedVolumeIdsAcrossDirectory.length}
              loading={isDeletingSelectedVolumes}
              onClick={handlers.confirmBatchDeleteVolumes}
            >
              批量删除卷纲
            </Button>
          </div>
          <Space size={6}>
            <Button size="small" danger icon={<Trash2 size={14} />} disabled={!hasGeneratedOutline} onClick={handlers.confirmClearOutline}>
              删除总纲
            </Button>
          </Space>
        </div>
      ) : null}
      <div className="outline-directory-scroll">
        <section className="outline-directory-section">
          <div className="outline-section-label"><FileText size={15} />总纲</div>
          <button className={`outline-tree-item is-primary ${selectedView === "outline" ? "is-active" : ""}`} onClick={() => handlers.setSelectedView("outline")}>
            <ScrollText size={18} />
            <span>总纲</span>
            <small>{hasGeneratedOutline ? "已生成" : "项目概览"}</small>
          </button>
        </section>
        {renderVolumeChapterTree()}
      </div>
    </aside>
  );
}
