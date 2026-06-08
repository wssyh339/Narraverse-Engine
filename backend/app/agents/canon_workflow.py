from __future__ import annotations

from pathlib import Path
from typing import Any

from app.schemas.canon import (
    CanonEntity,
    CanonRunRequest,
    CanonRunResult,
    CompletionStatus,
    DramaNode,
    DramaNodeType,
    EntityLevel,
    EntityType,
    ForeshadowingRecord,
    NovelCanon,
    NovelSeed,
    NovelState,
    UncertaintyTicket,
)
from app.services.canon_merge import CanonMergeNode
from app.services.entity_router import CanonCompletionRouter
from app.services.llm_provider import LLMProvider
from app.services.validators import ContinuityAgentValidator
from app.storage.canon_store import CanonStore, utc_now


CANON_AGENT_HANDOFFS: dict[str, list[str]] = {
    "StoryDirectorAgent": [
        "WhyInterrogatorAgent",
        "ThemeAgent",
        "WorldSettingAgent",
        "CharacterArcAgent",
        "ConflictAgent",
        "PlotArchitectAgent",
        "ContinuityAgent",
        "EntityExtractorAgent",
    ],
    "WhyInterrogatorAgent": [
        "ThemeAgent",
        "WorldSettingAgent",
        "CharacterArcAgent",
        "ConflictAgent",
        "PlotArchitectAgent",
        "ContinuityAgent",
    ],
    "ThemeAgent": ["CharacterArcAgent", "ConflictAgent", "PlotArchitectAgent", "CrisisClimaxAgent"],
    "WorldSettingAgent": [
        "RuleSystemAgent",
        "FactionSocietyAgent",
        "LocationAgent",
        "CharacterArcAgent",
        "ConflictAgent",
        "ContinuityAgent",
    ],
    "RuleSystemAgent": ["WorldSettingAgent", "FactionSocietyAgent", "ConflictAgent", "PlotArchitectAgent", "ContinuityAgent"],
    "FactionSocietyAgent": ["WorldSettingAgent", "CharacterArcAgent", "ConflictAgent", "PlotArchitectAgent", "ContinuityAgent"],
    "CharacterArcAgent": [
        "RelationshipAgent",
        "ConflictAgent",
        "ProgressiveComplicationAgent",
        "CrisisClimaxAgent",
        "ContinuityAgent",
    ],
    "RelationshipAgent": ["CharacterArcAgent", "ConflictAgent", "ProgressiveComplicationAgent", "ContinuityAgent"],
    "ConflictAgent": ["ProgressiveComplicationAgent", "CrisisClimaxAgent", "PlotArchitectAgent", "BeatControllerAgent"],
    "ProgressiveComplicationAgent": ["ConflictAgent", "CrisisClimaxAgent", "BeatControllerAgent", "PlotArchitectAgent"],
    "CrisisClimaxAgent": [
        "CharacterArcAgent",
        "ConflictAgent",
        "RuleSystemAgent",
        "ForeshadowingAgent",
        "BeatControllerAgent",
        "ContinuityAgent",
    ],
    "PlotArchitectAgent": ["BeatControllerAgent", "ForeshadowingAgent", "EntityExtractorAgent", "ContinuityAgent"],
    "BeatControllerAgent": ["ProgressiveComplicationAgent", "CrisisClimaxAgent", "ForeshadowingAgent", "ContinuityAgent"],
    "ForeshadowingAgent": ["PlotArchitectAgent", "BeatControllerAgent", "CharacterArcAgent", "ContinuityAgent"],
    "EntityExtractorAgent": [
        "CharacterArcAgent",
        "PlotArchitectAgent",
        "ItemLoreAgent",
        "FactionSocietyAgent",
        "LocationAgent",
        "RuleSystemAgent",
        "ForeshadowingAgent",
        "ContinuityAgent",
    ],
    "ItemLoreAgent": ["RuleSystemAgent", "WorldSettingAgent", "FactionSocietyAgent", "ForeshadowingAgent", "CrisisClimaxAgent", "ContinuityAgent"],
    "LocationAgent": ["WorldSettingAgent", "FactionSocietyAgent", "RuleSystemAgent", "PlotArchitectAgent", "CrisisClimaxAgent", "ContinuityAgent"],
    "ContinuityAgent": [
        "WorldSettingAgent",
        "RuleSystemAgent",
        "FactionSocietyAgent",
        "CharacterArcAgent",
        "RelationshipAgent",
        "ConflictAgent",
        "PlotArchitectAgent",
        "BeatControllerAgent",
        "ForeshadowingAgent",
        "StoryDirectorAgent",
    ],
}


class CanonWorkflow:
    def __init__(self, request: CanonRunRequest, *, base_dir: Path | str = "outputs") -> None:
        project_id = request.project_id or "canon_project"
        self.request = request.model_copy(update={"project_id": project_id})
        self.store = CanonStore(project_id=project_id, base_dir=base_dir)
        self.router = CanonCompletionRouter()
        self.merge = CanonMergeNode(self.router)
        self.validator = ContinuityAgentValidator()
        self.llm = LLMProvider()
        self.trace: list[str] = []
        self.trace_events: list[dict[str, Any]] = []

    def run(self) -> CanonRunResult:
        state = self._seed_interpreter()
        self._record("START")
        self._record("SeedInterpreterNode")
        self._why_question_node(state)
        self._story_director(state)

        extracted = self._entity_extractor(state)
        initial_merge = self.merge.merge_entities(self.store, extracted)
        state.canon_completion_tickets.extend(initial_merge.completion_tickets)
        state.continuity_issues.extend(initial_merge.continuity_issues)
        self._record("CanonCompletionRouter")

        completed_entities = self._complete_entities(extracted)
        completed_merge = self.merge.merge_entities(self.store, completed_entities)
        state.resolved_tickets.extend(ticket.ticket_id for ticket in state.canon_completion_tickets)
        state.continuity_issues.extend(completed_merge.continuity_issues)
        self._record("CanonMergeNode")

        self._conflict_agent(state)
        self._progressive_complication_agent(state)
        self._crisis_climax_agent(state)
        self._plot_architect_agent(state)
        self._beat_controller_agent(state)
        self._foreshadowing_agent(state)

        report = self.validator.validate_state(state, self.store)
        self._record("ContinuityAgent", {"report": report})
        final_outline = self._export(state, report)
        self._record("ExportNode")
        self.store.save_trace(self.trace_events)

        return CanonRunResult(
            project_id=state.project_id,
            state=state,
            canon_store_path=str(self.store.canon_path),
            trace_store_path=str(self.store.trace_path),
            version_store_path=str(self.store.version_path),
            final_outline_path=str(self.store.project_dir / "final_outline.md"),
            final_outline=final_outline,
            continuity_report=report,
            agent_trace=self.trace,
            drama_nodes=state.drama_nodes,
            canon_entities=self.store.list_entities(),
            completion_tickets=state.canon_completion_tickets,
            uncertainty_tickets=state.uncertainty_tickets,
            agent_handoff_graph=CANON_AGENT_HANDOFFS,
        )

    def _seed_interpreter(self) -> NovelState:
        seed = NovelSeed(
            worldview=self.request.worldview,
            one_sentence_story=self.request.one_sentence_story,
            genre=self.request.genre,
            target_length=self.request.target_length,
            tone=self.request.tone,
            reference_works=self.request.reference_works,
            avoid_elements=self.request.avoid_elements,
        )
        canon = NovelCanon(
            world_rules=["所有能源制度都围绕龙骨能源展开，资源规则会反过来压迫人物选择。"],
            power_system=["真龙封印不是万能力量，任何调用都必须付出身份暴露和肉身崩裂风险。"],
            history=["帝国以工业文明名义掩盖真龙灭绝史。"],
            social_order=["矿工阶层被制度化消耗，贵族与能源机构共享解释权。"],
            resources=["龙骨能源"],
            institutions=["帝国能源署"],
            secrets=["最后真龙封印"],
        )
        return NovelState(
            project_id=self.request.project_id or "canon_project",
            seed=seed,
            theme="被制度消耗的人如何夺回命运解释权。",
            canon=canon,
        )

    def _why_question_node(self, state: NovelState) -> None:
        self._record("WhyQuestionNode")
        state.why_logs.extend(
            [
                "为什么现在发生：龙骨矿脉进入衰竭期，帝国必须加速抽取最后真龙封印。",
                "为什么必须由主角经历：主角是封印容器，其他人只能围绕他争夺或误判。",
                "为什么不能逃避：矿籍、债务和封印反噬同时绑定主角。",
                "为什么读者会在意：私人逃亡会逐步揭开整个工业文明的道德债务。",
            ]
        )
        state.uncertainty_tickets.append(
            UncertaintyTicket(
                ticket_id="unc_000001",
                source_agent="WhyInterrogatorAgent",
                question="帝国为什么过去没有发现主角体内封印？",
                reason="这会影响反派迟迟未行动的合理性。",
                blocking_level=EntityLevel.A,
                suggested_agent="ContinuityAgent",
                related_entities=["secret:最后真龙封印", "faction:帝国能源署"],
            )
        )

    def _story_director(self, state: NovelState) -> None:
        self._record("StoryDirectorAgent", self.llm.generate("维护总体方向，先集中主线冲突。", agent_name="StoryDirectorAgent"))
        state.agent_trace.append("StoryDirectorAgent")

    def _entity_extractor(self, state: NovelState) -> list[CanonEntity]:
        self._record("EntityExtractorAgent")
        entities = [
            CanonEntity(
                name="最后龙裔矿工",
                entity_type=EntityType.CHARACTER,
                level=EntityLevel.S,
                story_function="主角命运、主题表达与最终危机选择的承载者。",
                first_appearance="SeedInterpreterNode",
                responsible_agent="EntityExtractorAgent",
                payload={"external_goal": "逃离龙骨矿区", "role_function": "被制度消耗者转为命运解释权争夺者"},
            ),
            CanonEntity(
                name="龙骨能源",
                entity_type=EntityType.ITEM,
                level=EntityLevel.S,
                story_function="驱动帝国制度、资源争夺、反派行动和高潮代价。",
                first_appearance="SeedInterpreterNode",
                responsible_agent="EntityExtractorAgent",
                payload={"item_type": "artifact_resource", "function": "维持帝国工业机器"},
            ),
            CanonEntity(
                name="帝国能源署",
                entity_type=EntityType.FACTION,
                level=EntityLevel.A,
                story_function="制度性反派，代表能源秩序和真相垄断。",
                first_appearance="SeedInterpreterNode",
                responsible_agent="EntityExtractorAgent",
                payload={"faction_type": "institution", "public_goal": "维持能源供给"},
            ),
            CanonEntity(
                name="龙骨矿区",
                entity_type=EntityType.LOCATION,
                level=EntityLevel.A,
                story_function="主角无法轻易离开的压迫空间和第一卷主要地图。",
                first_appearance="SeedInterpreterNode",
                responsible_agent="EntityExtractorAgent",
                payload={"location_type": "industrial_mine", "controller": "帝国能源署"},
            ),
            CanonEntity(
                name="最后真龙封印",
                entity_type=EntityType.SECRET,
                level=EntityLevel.S,
                story_function="推动身份反转、世界真相和最终高潮选择。",
                first_appearance="SeedInterpreterNode",
                responsible_agent="EntityExtractorAgent",
                payload={"truth": "主角体内封印着最后真龙"},
            ),
            CanonEntity(
                name="矿难觉醒事件",
                entity_type=EntityType.EVENT,
                level=EntityLevel.A,
                story_function="引爆主线，把主角从生存问题推入制度追捕。",
                first_appearance="INCITING_INCIDENT",
                responsible_agent="EntityExtractorAgent",
                payload={"event_type": "inciting_incident", "visible_event": "矿井坍塌后主角听见龙语"},
            ),
        ]
        state.characters.append(entities[0])
        return entities

    def _complete_entities(self, entities: list[CanonEntity]) -> list[CanonEntity]:
        completed: list[CanonEntity] = []
        for entity in entities:
            ticket = self.router.ticket_for_entity(entity)
            agent = ticket.suggested_agent if ticket else entity.responsible_agent
            self._record(agent)
            payload = {**entity.payload, **self._completion_payload(entity)}
            completed.append(
                entity.model_copy(
                    update={
                        "payload": payload,
                        "responsible_agent": agent,
                        "completion_status": CompletionStatus.COMPLETE,
                        "continuity_checked": True,
                    }
                )
            )
        return completed

    def _completion_payload(self, entity: CanonEntity) -> dict[str, Any]:
        name = entity.name
        common = {"if_removed_what_breaks": f"如果删除「{name}」，主线因果、危机代价或世界规则会失去支点。"}
        if entity.entity_type == EntityType.CHARACTER:
            return {
                **common,
                "external_goal": "逃离矿籍并活下去",
                "inner_need": "承认自己不能只做受害者，必须选择要成为什么人",
                "wrong_belief": "只要离开矿区就能摆脱帝国",
                "core_fear": "自己也是怪物和灾难源头",
                "core_desire": "拥有选择命运的权利",
                "secret": "体内封印着最后真龙",
                "relationship_to_protagonist": "本人",
                "relationship_to_main_conflict": "被所有势力争夺的冲突中心",
                "faction": "龙骨矿工",
                "power_or_skill": "能听见龙骨能源中的残响",
                "weakness": "每次调用力量都会暴露封印并撕裂身体",
                "arc_start": "低等矿工只求逃生",
                "arc_midpoint": "发现自己逃跑会让更多矿工被清算",
                "arc_crisis": "选择交出封印换个人自由，或公开真相引爆帝国追杀",
                "arc_climax": "主动释放部分真龙权柄，摧毁能源署的谎言机器",
                "arc_end": "从矿工变成新秩序的危险见证者",
                "why_this_character_must_exist": "只有封印容器本人能把私人苦难推向制度审判。",
                "future_use": "后续卷通过真龙记忆逐步揭开帝国历史。",
            }
        if entity.entity_type == EntityType.ITEM:
            return {
                **common,
                "origin": "真龙遗骨被帝国炼成能源网络",
                "creator": "第一代帝国炼金议会",
                "current_owner": "帝国能源署",
                "previous_owners": ["真龙族群", "第一代矿区军团"],
                "who_wants_it": ["帝国能源署", "叛乱矿工", "边境军阀"],
                "function": "为工业城市、军械和阶级制度供能",
                "limitation": "越高强度使用，越会唤醒真龙残魂",
                "cost": "消耗矿工寿命并污染土地",
                "risk": "封印破裂会让能源城市停摆",
                "symbolic_meaning": "以文明名义包装的掠夺",
                "first_appearance": "第一章矿井坍塌",
                "foreshadowing": "能源表盘在主角靠近时逆转",
                "major_use": "第一卷用残响证明矿难不是事故",
                "climax_use": "高潮中主角切断能源署核心反应炉",
                "why_it_exists": "把世界制度压力具体化为所有人依赖又恐惧的资源。",
                "why_now": "龙骨能源衰竭，帝国必须寻找最后封印。",
            }
        if entity.entity_type == EntityType.FACTION:
            return {
                **common,
                "hidden_goal": "找到最后真龙封印，延续能源垄断",
                "core_resource": "龙骨能源配额",
                "power_base": "矿籍制度、军警、能源许可证",
                "leader": "能源署总监赫连钧",
                "internal_split": "技术派想公开危机，贵族派想掩盖真相",
                "fear": "能源神话崩塌导致帝国合法性瓦解",
                "enemy_factions": ["矿工互助会", "边境自治军"],
                "ally_factions": ["帝都贵族", "军械厅"],
                "relationship_to_protagonist": "追捕、利用并试图定义主角身份",
                "relationship_to_antagonist": "为主要反派提供制度权力",
                "ideology": "文明必须由少数人掌控代价",
                "methods": "封锁真相、制造矿难记录、债务绑定",
                "weakness": "一旦能源代价公开，基层执行链会分裂",
                "role_in_conflict": "把私人逃亡升级为制度围剿",
                "role_in_climax": "在第一卷高潮中失去核心矿区解释权",
                "why_it_exists": "提供不可谈判的制度性阻力。",
            }
        if entity.entity_type == EntityType.LOCATION:
            return {
                **common,
                "geography": "建在古龙骸脊上的地下矿城",
                "history": "帝国建国初期第一座龙骨矿井",
                "controller": "帝国能源署",
                "population": "矿工、监工、能源技师和驻防军",
                "resources": "龙骨矿脉与封印残响",
                "danger": "塌方、能源病和监控军警",
                "secret": "矿区深处是最后真龙封印外壳",
                "social_order": "矿籍世袭，离矿需要偿还不可能偿清的债务",
                "visual_identity": "黑铁井架、蓝白龙骨火、潮湿矿尘",
                "story_function": "让主角从第一章开始无法轻易逃避",
                "first_appearance": "第一章矿井坍塌",
                "major_events": ["矿难觉醒", "矿工清算", "能源炉暴露"],
                "why_here": "只有矿区能同时呈现资源、阶级和封印真相。",
                "why_protagonist_must_go": "主角的工作、债务和封印源头都在这里。",
                "why_protagonist_cannot_easily_leave": "矿籍追踪、债务和封印反噬阻止逃离。",
            }
        if entity.entity_type == EntityType.SECRET:
            return {
                **common,
                "truth": "主角是最后真龙封印的人形容器",
                "who_knows": ["能源署总监赫连钧", "少数旧档案守护者"],
                "who_misunderstands": ["主角", "普通矿工"],
                "who_hides_it": ["帝国能源署"],
                "why_hidden": "公开真相会证明帝国工业文明建立在屠龙和奴役之上",
                "cost_if_revealed": "主角被追捕，矿区暴动，帝国能源市场崩塌",
                "false_explanation": "主角患有能源病",
                "foreshadowing_clues": ["龙骨火逆流", "旧档案缺页", "矿井深处传来龙语"],
                "reveal_timing": "第一卷卷末",
                "impact_on_character": "迫使主角从逃生者变成真相承担者",
                "impact_on_world": "能源合法性开始崩塌",
                "impact_on_conflict": "反派必须从灭口升级为夺取封印",
                "impact_on_climax": "决定主角是否释放真龙权柄",
                "why_not_revealed_earlier": "能源署伪造矿难记录并控制所有诊断权",
            }
        return {
            **common,
            "trigger": "龙骨能源衰竭导致旧封印松动",
            "hidden_cause": "能源署过度抽取",
            "protagonist_goal": "活着离开矿井",
            "opposition_force": "塌方、监工和封印反噬",
            "choice": "救同伴会暴露异常，不救则能暂时逃生",
            "cost": "暴露龙语能力并被能源署锁定",
            "new_information": "矿难不是事故，矿脉在寻找容器",
            "state_change": "主角从矿工变成被追捕目标",
            "consequence": "能源署开始封锁矿区",
            "next_event_caused": "矿工清算夜",
            "why_now": "龙骨能源衰竭到无法继续掩盖",
            "why_inevitable": "帝国越抽取，封印越接近破裂",
        }

    def _conflict_agent(self, state: NovelState) -> None:
        self._record("ConflictAgent")
        state.conflict_matrix.core_conflict = "主角想夺回命运解释权，帝国能源署要把他定义为资源容器。"
        state.conflict_matrix.escalation_path = [
            {"level": "私人阻碍", "cost": "主角失去矿工身份中的最后安全感"},
            {"level": "局部压迫", "cost": "矿区同伴被连坐"},
            {"level": "组织追捕", "cost": "主角必须公开部分异常能力"},
            {"level": "社会性污名", "cost": "帝国宣布他是能源病灾源"},
            {"level": "制度性围剿", "cost": "逃亡变成推翻解释权的战争"},
            {"level": "价值观决战", "cost": "主角必须牺牲个人自由换取真相公开"},
        ]

    def _progressive_complication_agent(self, state: NovelState) -> None:
        self._record("ProgressiveComplicationAgent")
        state.drama_nodes.extend(
            [
                DramaNode(
                    node_id="dn_001",
                    node_type=DramaNodeType.SETUP,
                    title="龙骨矿区的日常债务",
                    description="主角在矿籍制度下工作，任何离开都意味着债务清算。",
                    story_function="建立主角无法轻易逃避的制度牢笼。",
                    protagonist_goal="攒够离矿证",
                    opposition_force="矿籍债务和监工",
                    cost="失去自由时间和身体健康",
                    new_information="龙骨能源依赖矿工寿命",
                    state_change="读者理解世界压迫主角的方式",
                    next_node="dn_002",
                    why_chain=["为什么不能逃：债务与矿籍绑定。", "为什么读者在意：这是具体生活压力而非抽象设定。"],
                    related_entities=["location:龙骨矿区", "item:龙骨能源"],
                ),
                DramaNode(
                    node_id="dn_002",
                    node_type=DramaNodeType.INCITING_INCIDENT,
                    title="矿难中的龙语",
                    description="塌方时主角听见龙骨矿脉呼救，并用异常方式救出同伴。",
                    story_function="把私人逃生问题引向身份秘密和组织追捕。",
                    protagonist_goal="活着带同伴离开矿井",
                    opposition_force="塌方、监工封口、能源反噬",
                    cost="暴露龙语能力",
                    new_information="矿脉不是死物，主角与它有联系",
                    state_change="能源署开始锁定主角",
                    next_node="dn_003",
                    why_chain=["为什么现在：矿脉衰竭。", "为什么是主角：他是封印容器。"],
                    related_entities=["event:矿难觉醒事件", "secret:最后真龙封印"],
                ),
                DramaNode(
                    node_id="dn_003",
                    node_type=DramaNodeType.PROGRESSIVE_COMPLICATION,
                    title="救人后的清算",
                    description="主角表面救下同伴，实际让能源署有理由封锁整片矿区。",
                    story_function="主角的成功制造更大麻烦和道德压力。",
                    protagonist_goal="证明自己不是灾源",
                    opposition_force="能源署调查队",
                    cost="同伴被审讯，主角无法独自逃跑",
                    new_information="矿难记录被提前写好",
                    state_change="冲突从灾害升级为人为阴谋",
                    next_node="dn_004",
                    why_chain=["为什么不能简单逃：同伴被当成人质。", "为什么推动主线：揭露矿难有预谋。"],
                    related_entities=["faction:帝国能源署"],
                ),
            ]
        )

    def _crisis_climax_agent(self, state: NovelState) -> None:
        self._record("CrisisClimaxAgent")
        state.drama_nodes.extend(
            [
                DramaNode(
                    node_id="dn_004",
                    node_type=DramaNodeType.CRISIS,
                    title="交出封印或公开真相",
                    description="能源署提出交易：交出封印换个人自由，否则清算全矿区。",
                    story_function="危机是不可逆选择，逼主角在个人自由和共同真相之间付代价。",
                    protagonist_goal="保住自己和同伴",
                    opposition_force="能源署总监赫连钧",
                    cost="无论选择哪边都会失去一种安全",
                    new_information="主角不是病人，而是真龙封印容器",
                    state_change="主角被迫承认自身命运与世界真相绑定",
                    next_node="dn_005",
                    why_chain=["为什么不能拖延：清算令已发布。", "为什么没有第三条路：封印反噬进入倒计时。"],
                    related_entities=["secret:最后真龙封印", "faction:帝国能源署"],
                ),
                DramaNode(
                    node_id="dn_005",
                    node_type=DramaNodeType.CLIMAX,
                    title="切断核心反应炉",
                    description="主角执行选择，释放部分真龙权柄切断能源署核心反应炉。",
                    story_function="高潮是执行危机选择，用行动证明主题，而不是单纯大场面。",
                    protagonist_goal="公开真相并救下矿区",
                    opposition_force="能源署军警和失控反应炉",
                    cost="身体被龙骨火反噬，帝国正式通缉",
                    new_information="龙骨能源可以被封印容器反向关闭",
                    state_change="帝国能源神话第一次被公开击穿",
                    next_node="dn_006",
                    why_chain=["为什么兑现伏笔：前文龙骨火逆流成为反向关闭依据。", "为什么推动主题：主角夺回解释权。"],
                    related_entities=["item:龙骨能源", "secret:最后真龙封印"],
                ),
                DramaNode(
                    node_id="dn_006",
                    node_type=DramaNodeType.RESOLUTION,
                    title="矿区停火后的通缉令",
                    description="矿工短暂获救，但帝国把主角定义为能源灾源并发布通缉。",
                    story_function="结果承担选择后果，并把下一卷推向更大社会冲突。",
                    protagonist_goal="带着证据离开矿区",
                    opposition_force="帝国舆论机器",
                    cost="主角失去匿名生活",
                    new_information="边境自治军也在寻找真龙封印",
                    state_change="第一卷从矿区压迫转入帝国范围追捕",
                    next_node="dn_007",
                    why_chain=["为什么不是完胜：切断反应炉只摧毁局部解释权。", "为什么引向下一卷：更大势力开始入局。"],
                    related_entities=["faction:帝国能源署"],
                ),
            ]
        )

    def _plot_architect_agent(self, state: NovelState) -> None:
        self._record("PlotArchitectAgent")
        state.volume_outline = [
            {
                "volume": 1,
                "title": "第一卷：龙骨矿区",
                "core_map": "龙骨矿区",
                "mainline": "主角从矿难觉醒到公开真龙封印线索。",
                "ending_hook": "帝国通缉令把主角描述为会毁灭能源文明的灾源。",
            },
            {
                "volume": 2,
                "title": "第二卷：边境炉城",
                "core_map": "边境自治工业城",
                "mainline": "主角寻找能证明能源罪证的旧档案，同时被自治军利用。",
                "ending_hook": "旧档案显示真龙封印不止一个容器。",
            },
        ]

    def _beat_controller_agent(self, state: NovelState) -> None:
        self._record("BeatControllerAgent")
        state.chapter_outline = [
            {"chapter": index + 1, "function": node.story_function, "linked_node": node.node_id}
            for index, node in enumerate(state.drama_nodes[:10])
        ]

    def _foreshadowing_agent(self, state: NovelState) -> None:
        self._record("ForeshadowingAgent")
        state.foreshadowing_table = [
            ForeshadowingRecord(
                id="fs_001",
                clue="龙骨火在主角靠近时逆流",
                planted_at="第1章",
                payoff_plan="第一卷高潮用逆流原理关闭核心反应炉",
                status="planned",
                related_entities=["item:龙骨能源", "secret:最后真龙封印"],
            ),
            ForeshadowingRecord(
                id="fs_002",
                clue="矿难记录上的死亡时间早于塌方",
                planted_at="第3章",
                payoff_plan="揭示能源署提前知道矿难",
                status="planned",
                related_entities=["faction:帝国能源署"],
            ),
        ]

    def _export(self, state: NovelState, report: dict[str, Any]) -> str:
        self.store._ensure_dir()
        entities = self.store.list_entities()
        sections = [
            ("1. 故事核心种子", state.seed.model_dump(mode="json")),
            ("2. 主题问题", {"theme": state.theme, "正主题": "人必须夺回自身命运的解释权", "反主题": "文明可以要求个体永远牺牲"}),
            ("3. 正主题 / 反主题", {"正主题": "公开代价后的选择才是真正的文明", "反主题": "稳定可以掩盖一切掠夺"}),
            ("4. 世界观正典", state.canon.model_dump(mode="json")),
            ("5. 主要角色档案", [entity.model_dump(mode="json") for entity in entities if entity.entity_type == EntityType.CHARACTER]),
            ("6. 主要势力档案", [entity.model_dump(mode="json") for entity in entities if entity.entity_type == EntityType.FACTION]),
            ("7. 重要地点档案", [entity.model_dump(mode="json") for entity in entities if entity.entity_type == EntityType.LOCATION]),
            ("8. 重要物品档案", [entity.model_dump(mode="json") for entity in entities if entity.entity_type == EntityType.ITEM]),
            ("9. 秘密与真相表", [entity.model_dump(mode="json") for entity in entities if entity.entity_type == EntityType.SECRET]),
            ("10. 核心冲突矩阵", state.conflict_matrix.model_dump(mode="json")),
            ("11. 进展纠葛链", [node.model_dump(mode="json") for node in state.drama_nodes if node.node_type == DramaNodeType.PROGRESSIVE_COMPLICATION]),
            ("12. 危机 / 高潮 / 结果链", [node.model_dump(mode="json") for node in state.drama_nodes if node.node_type in {DramaNodeType.CRISIS, DramaNodeType.CLIMAX, DramaNodeType.RESOLUTION}]),
            ("13. 分卷大纲", state.volume_outline),
            ("14. DramaNode 节拍表", [node.model_dump(mode="json") for node in state.drama_nodes]),
            ("15. 伏笔与回收表", [item.model_dump(mode="json") for item in state.foreshadowing_table]),
            ("16. 连续性审查报告", report),
            ("17. 未解决问题列表", [item.model_dump(mode="json") for item in state.uncertainty_tickets]),
            ("18. 下一轮建议推演方向", ["扩展第二卷势力冲突", "补全反派赫连钧人物弧光", "为边境自治军建立 A 级势力档案"]),
        ]
        import json

        lines = ["# final_outline.md", ""]
        for title, content in sections:
            lines.extend([f"## {title}", "", "```json", json.dumps(content, ensure_ascii=False, indent=2), "```", ""])
        markdown = "\n".join(lines)
        (self.store.project_dir / "final_outline.md").write_text(markdown, encoding="utf-8")
        return markdown

    def _record(self, name: str, payload: dict[str, Any] | None = None) -> None:
        self.trace.append(name)
        self.trace_events.append({"agent": name, "payload": payload or {}, "created_at": utc_now()})
