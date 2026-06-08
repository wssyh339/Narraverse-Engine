from __future__ import annotations

from app.schemas.canon import CanonCompletionTicket, CanonEntity, EntityLevel, EntityType


REQUIRED_FIELDS: dict[EntityType, list[str]] = {
    EntityType.CHARACTER: [
        "external_goal",
        "inner_need",
        "wrong_belief",
        "core_fear",
        "core_desire",
        "secret",
        "relationship_to_main_conflict",
        "arc_start",
        "arc_midpoint",
        "arc_crisis",
        "arc_climax",
        "arc_end",
        "why_this_character_must_exist",
        "if_removed_what_breaks",
    ],
    EntityType.EVENT: [
        "trigger",
        "hidden_cause",
        "protagonist_goal",
        "opposition_force",
        "choice",
        "cost",
        "new_information",
        "state_change",
        "consequence",
        "next_event_caused",
        "why_now",
        "why_inevitable",
        "if_removed_what_breaks",
    ],
    EntityType.ITEM: [
        "origin",
        "current_owner",
        "who_wants_it",
        "function",
        "limitation",
        "cost",
        "risk",
        "symbolic_meaning",
        "foreshadowing",
        "major_use",
        "climax_use",
        "why_it_exists",
        "why_now",
        "if_removed_what_breaks",
    ],
    EntityType.FACTION: [
        "public_goal",
        "hidden_goal",
        "core_resource",
        "power_base",
        "leader",
        "internal_split",
        "fear",
        "enemy_factions",
        "relationship_to_protagonist",
        "ideology",
        "methods",
        "weakness",
        "role_in_conflict",
        "role_in_climax",
        "why_it_exists",
        "if_removed_what_breaks",
    ],
    EntityType.LOCATION: [
        "geography",
        "history",
        "controller",
        "resources",
        "danger",
        "secret",
        "social_order",
        "visual_identity",
        "story_function",
        "major_events",
        "why_here",
        "why_protagonist_must_go",
        "why_protagonist_cannot_easily_leave",
        "if_removed_what_breaks",
    ],
    EntityType.SECRET: [
        "truth",
        "who_knows",
        "who_misunderstands",
        "who_hides_it",
        "why_hidden",
        "cost_if_revealed",
        "false_explanation",
        "foreshadowing_clues",
        "reveal_timing",
        "impact_on_character",
        "impact_on_world",
        "impact_on_conflict",
        "impact_on_climax",
        "why_not_revealed_earlier",
        "if_removed_what_breaks",
    ],
    EntityType.RULE: ["scope", "limitation", "cost", "exception", "why_it_exists", "if_removed_what_breaks"],
    EntityType.RESOURCE: ["source", "scarcity", "controller", "cost", "conflict_function", "if_removed_what_breaks"],
    EntityType.INSTITUTION: ["public_role", "hidden_role", "rules", "weakness", "conflict_function", "if_removed_what_breaks"],
    EntityType.SYMBOL: ["meaning", "first_appearance", "foreshadowing", "payoff", "theme_connection"],
    EntityType.RELATIONSHIP: ["parties", "desire", "fear", "power_imbalance", "conflict_function"],
}


AGENT_BY_TYPE: dict[EntityType, str] = {
    EntityType.CHARACTER: "CharacterArcAgent",
    EntityType.EVENT: "PlotArchitectAgent",
    EntityType.ITEM: "ItemLoreAgent",
    EntityType.FACTION: "FactionSocietyAgent",
    EntityType.LOCATION: "LocationAgent",
    EntityType.SECRET: "ForeshadowingAgent",
    EntityType.RULE: "RuleSystemAgent",
    EntityType.RESOURCE: "WorldSettingAgent",
    EntityType.INSTITUTION: "FactionSocietyAgent",
    EntityType.SYMBOL: "ThemeAgent",
    EntityType.RELATIONSHIP: "RelationshipAgent",
}


def requires_completion(level: EntityLevel) -> bool:
    return level in {EntityLevel.S, EntityLevel.A}


class CanonCompletionRouter:
    def missing_fields(self, entity: CanonEntity) -> list[str]:
        required = REQUIRED_FIELDS.get(entity.entity_type, [])
        return [field for field in required if entity.payload.get(field) in (None, "", [], {})]

    def suggested_agent_for(self, entity: CanonEntity) -> str:
        if entity.entity_type == EntityType.EVENT:
            event_type = str(entity.payload.get("event_type", "")).lower()
            if "crisis" in event_type or "climax" in event_type or "危机" in event_type or "高潮" in event_type:
                return "CrisisClimaxAgent"
        if entity.entity_type == EntityType.ITEM:
            item_type = str(entity.payload.get("item_type", "")).lower()
            if any(keyword in item_type for keyword in ["artifact", "神器", "ability", "technology", "科技", "能力"]):
                return "RuleSystemAgent"
        return AGENT_BY_TYPE.get(entity.entity_type, "StoryDirectorAgent")

    def ticket_for_entity(self, entity: CanonEntity) -> CanonCompletionTicket | None:
        missing = self.missing_fields(entity)
        if not missing and (not requires_completion(entity.level) or entity.continuity_checked):
            return None
        if not requires_completion(entity.level) and not missing:
            return None
        return CanonCompletionTicket(
            ticket_id=f"cct_{abs(hash((entity.key, tuple(missing)))) % 10**12:012d}",
            entity_name=entity.name,
            entity_type=entity.entity_type,
            entity_level=entity.level,
            missing_fields=missing,
            suggested_agent=self.suggested_agent_for(entity),
            reason=(
                "S / A 级实体必须补全后才能进入正式大纲。"
                if requires_completion(entity.level)
                else "B 级实体存在缺失字段，建议轻量补全。"
            ),
        )
