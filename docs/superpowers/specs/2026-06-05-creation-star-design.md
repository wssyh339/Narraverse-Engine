# Creation Star Design

## Goal

Add a workspace-first "创作 Star" card-drawing flow that helps authors establish market-facing novel direction, worldbuilding, protagonist setup, project thesis, and world rules before formal generation.

## Scope

- Add a dedicated `creation_star` Agent with a detailed prompt.
- Add backend APIs for option metadata, staged card drawing, and user-confirmed commit.
- Keep final writes user-confirmed. AI-generated cards are suggestions until `commit`.
- Persist confirmed output into existing project, story bible, character, story entity, world fact, graph, version, and agent-run structures.
- Add the first button in the workspace top toolbar.
- Use existing React, Ant Design, Axios, FastAPI, SQLAlchemy, and pydantic stack.

## Flow

1. Basic information: channel, genre, subgenre, tags, reader, target words, style, and manual inputs.
2. Worldview cards: nine editable cards generated from the selected basic information.
3. Protagonist cards: multiple editable protagonist cards generated from the selected world and tags.
4. Bible and rule cards: editable project bible and world-rule table.
5. Commit: update project profile and story bible, create/update protagonist, create world facts/entities, graph nodes, agent run, and snapshot.

## Data Contract

`GET /api/creation-star/options` returns channel, genre, subgenre, tag, style, and target-word options.

`POST /api/projects/{project_id}/creation-star/draw` accepts:

```json
{
  "step": "worldview",
  "basic_info": {},
  "selected_worldview": {},
  "selected_protagonist": {},
  "project_bible": {},
  "world_rules": {},
  "manual_input": "",
  "count": 9
}
```

`POST /api/projects/{project_id}/creation-star/commit` accepts the final edited selections and writes them to the existing canon tables.

