# 35. 章节写前准备提示词

本提示词用于已确认章纲之后、章节卡之前。
它不是全书大纲生成入口，只负责把当前章节的写作边界、正典依赖、伏笔提醒和字数预算固化下来。

```text
请根据以下资料，为当前章节生成写前准备。

已确认当前章纲：

【粘贴 current_chapter_outline】

canon_context：

【粘贴 canon_context】

叙事账本：

【粘贴 narrative_ledger】

参考资产：

【粘贴 reference_assets，可为空】

用户额外要求：

【粘贴 user_instruction，可为空】

要求：

1. 不要重写全书大纲、卷纲或章纲。
2. 不要新增未经提示的主线方向。
3. 必须保留已确认章纲中的章节编号、标题、核心危机、结果和章末钩子。
4. 必须明确本章在长篇结构中的位置，例如开局、推进、反转、承压、收束。
5. 必须明确本章目标情绪变化和读者追读理由。
6. 必须列出本章必须读取或兑现的正典点。
7. 必须列出本章需要推进、强化、回收或避免误伤的伏笔。
8. 必须给出 target/min/max 字数预算。
9. 必须列出本章写作时要避免的问题。
10. 只输出严格 JSON object。

输出 JSON schema：

{
  "chapter_no": 1,
  "chapter_title": "第1章：标题",
  "chapter_position": "推进",
  "target_emotion": "压迫后转为反击",
  "pressure_level": 6,
  "reader_pull_reason": "读者想知道主角下一步如何处理新代价",
  "required_canon": ["必须读取或兑现的正典点"],
  "open_foreshadowing": ["需要推进或避开的伏笔"],
  "previous_summary": "前文必要摘要",
  "word_budget": {
    "target": 4000,
    "min": 3200,
    "max": 4800
  },
  "must_avoid": ["本章必须避免的问题"]
}
```

---
