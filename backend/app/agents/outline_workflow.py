from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.agents.outline_agents import AGENT_CLASS_BY_NAME, CLASS_NAME_TO_AGENT_NAME
from app.agents.outline_llm_client import MockOutlineLLMClient, OutlineLLMClient
from app.agents.outline_models import (
    AuditIssue,
    AuditReport,
    BeatSheet,
    CharacterProfile,
    ForeshadowingItem,
    ProjectConfig,
    ProtagonistArc,
    StoryKernel,
    StoryState,
    VolumeOutline,
    WorldBible,
)
from app.agents.outline_storage import save_markdown_exports


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class GateValidator:
    def _result(self, gate: str, issues: list[str]) -> dict[str, Any]:
        return {"gate": gate, "passed": not issues, "issues": issues}

    def validate_story_kernel(self, kernel: StoryKernel) -> dict[str, Any]:
        score = kernel.suitability_score or 0
        if score > 10:
            score = score / 10
        issues = []
        if not kernel.protagonist_desire:
            issues.append("主角欲望不明确")
        if not kernel.core_conflict:
            issues.append("核心矛盾不明确")
        if not kernel.failure_cost:
            issues.append("失败代价不明确")
        if len(kernel.long_term_engines) < 5:
            issues.append("长期推进引擎少于5个")
        if not kernel.ending_directions:
            issues.append("缺少终局方向")
        if score < 8:
            issues.append("长篇适配度低于8分")
        return self._result("Gate 1：故事核心", issues)

    def validate_world_bible(self, world_bible: WorldBible) -> dict[str, Any]:
        power_system = world_bible.power_system
        issues = []
        if len(world_bible.base_rules) < 5:
            issues.append("基础规则少于5条")
        if len(world_bible.factions) < 4:
            issues.append("主要势力少于4个")
        if len(world_bible.map_layers) < 5:
            issues.append("地图层级少于5层")
        if not power_system.get("levels") or not power_system.get("limits") or not power_system.get("cost"):
            issues.append("力量体系缺少等级、限制或代价")
        if not world_bible.final_secret:
            issues.append("缺少世界终局秘密")
        if len(world_bible.historical_secrets) < 3:
            issues.append("历史暗线少于3条")
        return self._result("Gate 2：世界圣经", issues)

    def validate_character_system(self, state: StoryState) -> dict[str, Any]:
        issues = []
        if len(state.characters) < 8:
            issues.append("核心人物少于8个")
        if len(state.protagonist_arcs) < state.config.target_volumes:
            issues.append("主角成长线未覆盖全部卷")
        weak_characters = [item.name for item in state.characters if not item.deep_desire]
        if weak_characters:
            issues.append(f"人物缺少欲望：{', '.join(weak_characters[:5])}")
        villain_chain = state.faction_conflicts.get("villain_chain", [])
        if len(villain_chain) < state.config.target_volumes:
            issues.append("反派链未覆盖全部卷")
        cross_volume_arcs = [item for item in state.characters if item.arc]
        if len(cross_volume_arcs) < 3:
            issues.append("跨卷人物弧光少于3条")
        return self._result("Gate 3：人物系统", issues)

    def validate_full_structure(self, state: StoryState) -> dict[str, Any]:
        issues = []
        if len(state.volumes) < state.config.target_volumes:
            issues.append("分卷数量不足")
        for volume in state.volumes:
            if not volume.core_map:
                issues.append(f"第{volume.volume}卷缺少地图")
            if not volume.main_plot:
                issues.append(f"第{volume.volume}卷缺少主线")
            if not volume.hidden_plot:
                issues.append(f"第{volume.volume}卷缺少暗线")
            if not volume.protagonist_upgrade:
                issues.append(f"第{volume.volume}卷缺少主角提升")
            if not volume.final_hook:
                issues.append(f"第{volume.volume}卷缺少卷末钩子")
        if not state.full_structure.get("ending_closure_design"):
            issues.append("结局闭环设计缺失")
        return self._result("Gate 4：全书结构", issues)

    def validate_single_volume(self, volume: VolumeOutline) -> dict[str, Any]:
        issues = []
        if len(volume.phases) != 5:
            issues.append("单卷必须包含5个Phase")
        for index, phase in enumerate(volume.phases, start=1):
            events = phase.get("major_events") or [
                value for key, value in phase.items() if str(key).startswith("大事件") and value
            ]
            if len(events) < 5:
                issues.append(f"Phase {index} 大事件少于5个")
        if not volume.main_plot:
            issues.append("本卷目标/主线不明确")
        if not volume.hidden_plot:
            issues.append("本卷暗线不明确")
        if not volume.final_hook:
            issues.append("本卷钩子不明确")
        if not volume.foreshadowing_plot:
            issues.append("本卷伏笔变动不明确")
        return self._result("Gate 5：单卷结构", issues)

    def validate_global(self, state: StoryState) -> dict[str, Any]:
        issues: list[str] = []
        for check in [
            self.validate_story_kernel(state.kernel),
            self.validate_world_bible(state.world_bible),
            self.validate_character_system(state),
            self.validate_full_structure(state),
        ]:
            issues.extend(check["issues"])
        if not state.foreshadowing_ledger:
            issues.append("伏笔账本为空")
        if not state.beat_sheets:
            issues.append("章节节拍表为空")
        return self._result("Gate 6：全局闭环", issues)


class RevisionRouter:
    ROUTES = [
        (("主角目标不清", "主角欲望不清", "欲望不明确"), "OneSentenceExpansionAgent"),
        (("世界规则混乱", "世界规则冲突", "世界观混乱"), "WorldBibleAgent"),
        (("战力膨胀", "金手指万能", "能力万能"), "PowerSystemAgent"),
        (("配角工具化", "工具人"), "CharacterTreeAgent"),
        (("势力冲突弱", "冲突弱"), "FactionConflictAgent"),
        (("卷与卷割裂", "结局突兀"), "FullStructureAgent"),
        (("单卷节奏弱", "节奏弱"), "VolumeOutlineAgent"),
        (("爽点重复", "节拍重复"), "BeatControlAgent"),
        (("伏笔没回收", "伏笔未回收", "只埋不收"), "ForeshadowingAgent"),
    ]

    def route_issue(self, issue_text: str) -> str:
        for keywords, agent_name in self.ROUTES:
            if any(keyword in issue_text for keyword in keywords):
                return agent_name
        return "EditorOrchestratorAgent"


class NovelWorkflow:
    def __init__(
        self,
        config: ProjectConfig,
        raw_worldview: str = "",
        one_sentence_story: str = "",
        client: OutlineLLMClient | None = None,
    ) -> None:
        self.client = client or MockOutlineLLMClient()
        self.gate_validator = GateValidator()
        self.revision_router = RevisionRouter()
        self.state = StoryState(
            config=config,
            raw_worldview=raw_worldview,
            kernel=StoryKernel(one_sentence_story=one_sentence_story),
        )

    def _call_agent(self, agent_name: str, **kwargs: Any) -> dict[str, Any]:
        agent_class = AGENT_CLASS_BY_NAME[agent_name]
        output = agent_class(client=self.client).run(self.state, **kwargs)
        self.state.revision_history.append(
            {
                "time": _now_iso(),
                "agent_name": agent_name,
                "stage": self.state.current_stage,
                "output": output,
            }
        )
        return output

    def run_single_agent(self, agent_name: str, **kwargs: Any) -> dict[str, Any]:
        normalized = CLASS_NAME_TO_AGENT_NAME.get(agent_name, agent_name)
        if normalized not in AGENT_CLASS_BY_NAME:
            raise ValueError(f"未知 Agent：{agent_name}")
        output = self._call_agent(normalized, **kwargs)
        self._apply_agent_result(normalized, **kwargs)
        return output

    def run_until_stage(self, stage_name: str) -> StoryState:
        order = ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10", "S11", "S12", "S13"]
        target = stage_name.upper()
        if target not in order:
            raise ValueError(f"未知阶段：{stage_name}")
        for stage in order:
            if stage == "S1":
                self.run_single_agent("one_sentence_expansion")
            elif stage == "S2":
                self.run_single_agent("genre_market_position")
            elif stage == "S3":
                self.run_single_agent("world_bible")
            elif stage == "S4":
                self.run_single_agent("protagonist_arc")
            elif stage == "S5":
                self.run_single_agent("character_tree")
                self.run_single_agent("faction_conflict")
                self.run_single_agent("power_system")
            elif stage == "S6":
                self.run_single_agent("editor_orchestrator")
            elif stage == "S7":
                self.run_single_agent("full_structure")
            elif stage == "S8":
                self.run_single_agent("foreshadowing_manager")
            elif stage == "S9":
                for volume_number in range(1, self.state.config.target_volumes + 1):
                    self.run_volume(volume_number)
            elif stage == "S10":
                self.state.current_stage = "S10"
            elif stage == "S11":
                self.audit_current_state()
            elif stage == "S12":
                self._run_revision_if_needed()
            elif stage == "S13":
                self.state.current_stage = "S13"
            if stage == target:
                break
        return self.state

    def run_full_pipeline(self) -> StoryState:
        return self.run_until_stage("S13")

    def run_volume(self, volume_number: int) -> VolumeOutline:
        self._call_agent("volume_outline", volume_number=volume_number)
        volume = self._build_volume(volume_number)
        self._replace_volume(volume)
        self._call_agent("beat_control", volume_number=volume_number)
        self._replace_beat_sheet(self._build_beat_sheet(volume_number))
        self._call_agent("foreshadowing_manager", volume_number=volume_number)
        self._upsert_foreshadowing(volume_number)
        gate = self.gate_validator.validate_single_volume(volume)
        self.state.audit_reports.append(self._audit_report(f"volume_{volume_number}", gate))
        self.state.current_stage = f"S9_VOLUME_{volume_number}"
        return volume

    def audit_current_state(self) -> AuditReport:
        self._call_agent("logic_audit")
        gate = self.gate_validator.validate_global(self.state)
        report = self._audit_report("global", gate)
        self.state.audit_reports.append(report)
        self.state.current_stage = "S11"
        return report

    def export_final_outline(self, export_dir: str | Path = "./workspace/exports") -> list[Path]:
        return save_markdown_exports(self.state, export_dir)

    def _apply_agent_result(self, agent_name: str, **kwargs: Any) -> None:
        if agent_name == "one_sentence_expansion":
            self.state.kernel = self._build_kernel()
            self.state.current_stage = "S1"
        elif agent_name == "genre_market_position":
            self.state.market_position = self._build_market_position()
            self.state.current_stage = "S2"
        elif agent_name == "world_bible":
            self.state.world_bible = self._build_world_bible()
            self.state.current_stage = "S3"
        elif agent_name == "protagonist_arc":
            self.state.protagonist_arcs = self._build_protagonist_arcs()
            self.state.current_stage = "S4"
        elif agent_name == "character_tree":
            self.state.characters = self._build_characters()
            self.state.current_stage = "S5"
        elif agent_name == "faction_conflict":
            self.state.faction_conflicts = self._build_faction_conflicts()
            self.state.current_stage = "S5"
        elif agent_name == "power_system":
            self.state.power_progression = self._build_power_progression()
            self.state.current_stage = "S5"
        elif agent_name == "editor_orchestrator":
            self.state.current_stage = "S6"
        elif agent_name == "full_structure":
            self.state.full_structure = self._build_full_structure()
            self.state.current_stage = "S7"
        elif agent_name == "foreshadowing_manager":
            volume_number = kwargs.get("volume_number")
            if volume_number:
                self._upsert_foreshadowing(int(volume_number))
            elif not self.state.foreshadowing_ledger:
                for index in range(1, self.state.config.target_volumes + 1):
                    self._upsert_foreshadowing(index)
            self.state.current_stage = "S8"
        elif agent_name == "volume_outline":
            self._replace_volume(self._build_volume(int(kwargs.get("volume_number", 1))))
            self.state.current_stage = "S9"
        elif agent_name == "beat_control":
            self._replace_beat_sheet(self._build_beat_sheet(int(kwargs.get("volume_number", 1))))
            self.state.current_stage = "S10"
        elif agent_name == "logic_audit":
            gate = self.gate_validator.validate_global(self.state)
            self.state.audit_reports.append(self._audit_report("global", gate))
            self.state.current_stage = "S11"

    def _run_revision_if_needed(self) -> None:
        latest = self.state.audit_reports[-1] if self.state.audit_reports else self.audit_current_state()
        if latest.passed:
            self.state.current_stage = "S12"
            return
        issue_text = latest.issues[0].issue if latest.issues else "综合失控"
        routed = self.revision_router.route_issue(issue_text)
        self.state.revision_history.append({"time": _now_iso(), "stage": "S12", "routed_agent": routed, "issue": issue_text})
        self.state.current_stage = "S12"

    def _audit_report(self, stage: str, gate: dict[str, Any]) -> AuditReport:
        issues = [
            AuditIssue(
                severity="A" if index == 0 else "B",
                issue=issue,
                location=stage,
                reason="未达到固定 Gate 验收标准",
                suggestion=f"调用 {self.revision_router.route_issue(issue)} 返工",
            )
            for index, issue in enumerate(gate["issues"])
        ]
        return AuditReport(
            stage=stage,
            conclusion="通过" if gate["passed"] else "需要返工",
            issues=issues,
            passed=gate["passed"],
            next_agent=None if gate["passed"] else self.revision_router.route_issue(issues[0].issue),
            revision_required=not gate["passed"],
        )

    def _build_kernel(self) -> StoryKernel:
        story = self.state.kernel.one_sentence_story or f"{self.state.config.project_name}的主角在{self.state.config.genre}世界中追求真相。"
        return StoryKernel(
            one_sentence_story=story,
            core_story=f"{story} 这条故事线通过欲望、阻力、代价和终局秘密持续升级。",
            protagonist_desire="夺回命运解释权，并把个人异常转化为改变世界规则的力量。",
            core_conflict="主角的长期欲望与维护旧秩序的势力持续冲突。",
            failure_cost="主角失去同伴、身份和揭开真相的机会，世界继续被旧规则吞噬。",
            long_term_engines=["卷级地图升级", "势力围剿", "能力代价", "人物秘密", "终局真相", "伏笔回收"],
            ending_directions=["主角建立新规则", "旧秩序被重写", "核心矛盾闭环"],
            suitability_score=8.8,
        )

    def _build_market_position(self) -> dict[str, Any]:
        return {
            "type_positioning": {"main_type": self.state.config.genre, "sub_types": ["升级", "悬疑暗线", "势力博弈"], "tags": [self.state.config.genre, self.state.config.tone, "长线伏笔"]},
            "target_readers": f"喜欢{self.state.config.genre}、{self.state.config.tone}、强钩子和持续升级的读者。",
            "core_selling_points": ["主角欲望清晰", "规则持续制造压迫", "每卷有势力破防"],
            "differentiation": "用总编状态机控制因果链，不把大纲写成散点脑洞。",
            "core_emotions": ["爽", "燃", "悬疑", "反转", "压迫"],
            "satisfaction_types": ["规则套利", "弱势反打", "身份翻转", "势力破防", "旧案揭露", "代价换胜", "卷末钩子", "关系反转"],
            "fatigue_risks": ["同一爽点重复", "反派只负责震惊", "能力无代价解决一切"],
            "type_boundaries": ["不写正文", "不机械降神", "不提前揭底"],
        }

    def _build_world_bible(self) -> WorldBible:
        return WorldBible(
            world_summary=self.state.raw_worldview or f"{self.state.config.genre}世界以隐藏规则和资源分配压迫主角。",
            base_rules=[f"世界规则{i}：所有力量都需要代价和触发条件。" for i in range(1, 6)],
            power_system={
                "levels": [f"阶段{i}" for i in range(1, 6)],
                "source": "异常规则/核心资源",
                "upgrade_method": "通过行动、资源、认知和关系代价逐卷升级。",
                "cost": "资源、身份、关系或心理稳定性。",
                "limits": "不能跳过前置认知；越级使用会反噬。",
                "loss_of_control_risk": "敌人识破机制后可反向设置陷阱。",
            },
            social_structure={"surface_society": "公开秩序", "inner_society": "掌控资源和真相的隐层秩序"},
            factions=[
                {"name": f"势力{i}", "goal": "维持自身资源优势", "conflicts_it_can_create": ["封锁", "误导", "围剿"]}
                for i in range(1, 5)
            ],
            resources=[{"name": f"核心资源{i}", "plot_value": "争夺、交换和代价"} for i in range(1, 5)],
            map_layers=[f"地图层级{i}" for i in range(1, 6)],
            historical_secrets=[f"历史暗线{i}" for i in range(1, 4)],
            final_secret="终局真相是旧秩序长期扭曲规则分配的结果。",
            forbidden_changes=self.state.config.forbidden_elements or ["无铺垫复活", "机械降神"],
        )

    def _build_protagonist_arcs(self) -> list[ProtagonistArc]:
        return [
            ProtagonistArc(
                volume=volume,
                external_goal=f"解决第{volume}卷阶段目标",
                internal_change="从被动求生到主动定义规则",
                ability_change=f"解锁第{volume}阶段能力用法",
                relationship_change="新增羁绊、债务或背叛风险",
                cost="暴露能力线索并承担关系代价",
            )
            for volume in range(1, self.state.config.target_volumes + 1)
        ]

    def _build_characters(self) -> list[CharacterProfile]:
        roles = ["主角", "宿敌", "盟友", "导师", "竞争者", "背叛者", "见证者", "终局反派"]
        return [
            CharacterProfile(
                name=f"{role}{index}",
                initial_identity=f"{self.state.config.genre}世界中的{role}",
                faction="主角阵营" if index in {1, 3, 4} else "对立/中立阵营",
                first_volume=max(1, min(index, self.state.config.target_volumes)),
                surface_goal="获得资源和安全位置",
                deep_desire="证明自身选择不是被规则操控的结果",
                secret=f"跨卷秘密{index}",
                relation_to_protagonist_start="陌生/试探",
                relation_to_protagonist_end="信任、背叛或终局对照",
                representative_conflict="价值观和资源选择冲突",
                arc="跨卷推进的人物弧光",
                final_fate="在终局见证新规则",
            )
            for index, role in enumerate(roles, start=1)
        ]

    def _build_faction_conflicts(self) -> dict[str, Any]:
        return {
            "core_conflict_one_sentence": "主角改写规则的欲望与旧秩序维护者的利益相撞。",
            "factions": [f"势力{i}" for i in range(1, 5)],
            "villain_chain": [
                {
                    "volume": volume,
                    "villain": f"第{volume}卷反派",
                    "desire": "维护阶段利益",
                    "why_against_protagonist": "主角破坏其资源分配",
                    "how_they_fail": "被主角利用规则漏洞反制",
                    "consequence_after_failure": "暴露更高层势力",
                }
                for volume in range(1, self.state.config.target_volumes + 1)
            ],
            "local_to_global_escalation_path": "从局部规则异常升级到全局秩序崩解。",
        }

    def _build_power_progression(self) -> dict[str, Any]:
        return {
            "cheat_one_sentence": "主角能识别并利用世界规则漏洞，但每次使用都会制造新的代价。",
            "basic_rules": {"trigger_condition": "发现规则矛盾", "reward_mechanism": "获得阶段资源", "side_effects": "被敌人记录特征"},
            "upgrade_route": [
                {"volume": volume, "unlocked_ability": f"能力{volume}", "limit": "必须满足前置认知", "cost": "关系或身份代价"}
                for volume in range(1, self.state.config.target_volumes + 1)
            ],
            "enemy_counter_methods": ["伪造规则", "诱导越级", "封锁资源", "制造舆论", "控制同伴"],
            "failure_scenarios": ["情报不足", "代价无法承受", "敌人提前布置反制"],
            "power_inflation_control": {"abilities_to_delay": ["终局级改写"], "abilities_requiring_cost": ["越级破局"]},
        }

    def _build_full_structure(self) -> dict[str, Any]:
        return {
            "full_story_one_sentence": self.state.kernel.one_sentence_story,
            "story_stages": ["前三卷立住卖点", "中三卷扩张真相", "后三卷终局压迫", "最终卷闭环"],
            "ten_volume_table": [
                {
                    "volume": volume,
                    "title": f"第{volume}卷：阶段升级",
                    "map": f"地图层级{volume}",
                    "main_conflict": f"第{volume}卷阶段冲突",
                    "final_hook": f"第{volume}卷末通向下一层真相",
                }
                for volume in range(1, self.state.config.target_volumes + 1)
            ],
            "upgrade_curve": self.state.power_progression.get("upgrade_route", []),
            "ending_closure_design": "终局回收核心矛盾、主角欲望、世界规则和主要伏笔。",
        }

    def _build_volume(self, volume_number: int) -> VolumeOutline:
        start = (volume_number - 1) * self.state.config.chapters_per_volume + 1
        end = volume_number * self.state.config.chapters_per_volume
        phases = []
        phase_titles = ["目标 + 主线引入", "阻碍 + 支线并行", "伏笔揭露 + 多转折铺垫", "爆发 + 情绪释放", "收尾 + 地位转化"]
        for index, title in enumerate(phase_titles, start=1):
            phases.append(
                {
                    "phase": index,
                    "title": title,
                    "major_events": [f"第{volume_number}卷Phase{index}大事件{event}" for event in range(1, 6)],
                    "foreshadowing_change": "埋设、误导、推进或回收至少一个伏笔",
                }
            )
        return VolumeOutline(
            volume=volume_number,
            title=f"第{volume_number}卷：阶段升级",
            chapter_range=f"{start}-{end}",
            core_map=f"地图层级{volume_number}",
            main_plot=f"主角完成第{volume_number}卷阶段目标并让一个势力破防。",
            hidden_plot="终局真相推进一格，但不直接揭底。",
            character_plot="至少一个关系发生不可逆变化。",
            foreshadowing_plot="本卷伏笔有埋设、误导、推进和回收节点。",
            protagonist_upgrade={"ability": f"第{volume_number}阶段能力", "status": "获得新的社会反馈"},
            phases=phases,
            final_hook=f"第{volume_number}卷末发现下一层规则入口。",
            change_summary={"protagonist": "目标、能力、地位和关系均发生变化"},
            risks=[],
        )

    def _build_beat_sheet(self, volume_number: int) -> BeatSheet:
        return BeatSheet(
            volume=volume_number,
            emotional_curve="压迫 -> 试探 -> 误判 -> 反打 -> 钩子",
            phase_beats=[{"phase": index, "function": "目标/阻力/转折/释放/钩子"[0:]} for index in range(1, 6)],
            ten_chapter_loops=[
                {"range": f"{start}-{start + 9}", "loop": "目标、阻碍、回报、钩子形成小闭环"}
                for start in range((volume_number - 1) * self.state.config.chapters_per_volume + 1, volume_number * self.state.config.chapters_per_volume + 1, 10)
            ],
            chapter_functions=[
                {"chapter": chapter, "function": "推进主线并制造追读点"}
                for chapter in range((volume_number - 1) * self.state.config.chapters_per_volume + 1, volume_number * self.state.config.chapters_per_volume + 1)
            ],
            repetition_check=[],
            revision_suggestions=[],
        )

    def _upsert_foreshadowing(self, volume_number: int) -> None:
        item_id = f"F{volume_number:03d}"
        existing = {item.id: item for item in self.state.foreshadowing_ledger}
        existing[item_id] = ForeshadowingItem(
            id=item_id,
            name=f"第{volume_number}卷核心伏笔",
            first_appearance=f"第{(volume_number - 1) * self.state.config.chapters_per_volume + 1}章",
            surface_meaning="看似普通的异常细节",
            true_meaning="指向终局规则或人物秘密",
            related_characters=["主角1"],
            related_factions=[f"势力{max(1, min(volume_number, 4))}"],
            importance="high" if volume_number in {1, self.state.config.target_volumes} else "medium",
            progress_nodes=[f"第{volume_number * self.state.config.chapters_per_volume - 20}章"],
            misdirection_nodes=[f"第{volume_number * self.state.config.chapters_per_volume - 10}章"],
            payoff_node=f"第{volume_number * self.state.config.chapters_per_volume}章",
            payoff_method="在卷末反转中回收或升级解释",
            status="planted" if volume_number < self.state.config.target_volumes else "paid_off",
            risk=None,
        )
        self.state.foreshadowing_ledger = [existing[key] for key in sorted(existing)]

    def _replace_volume(self, volume: VolumeOutline) -> None:
        remaining = [item for item in self.state.volumes if item.volume != volume.volume]
        remaining.append(volume)
        self.state.volumes = sorted(remaining, key=lambda item: item.volume)

    def _replace_beat_sheet(self, beat_sheet: BeatSheet) -> None:
        remaining = [item for item in self.state.beat_sheets if item.volume != beat_sheet.volume]
        remaining.append(beat_sheet)
        self.state.beat_sheets = sorted(remaining, key=lambda item: item.volume)
