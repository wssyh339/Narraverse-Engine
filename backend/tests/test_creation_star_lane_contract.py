from __future__ import annotations

from app.agents.creation_star.service import build_creation_star_state
from app.agents.creation_star.state import CreationStarState


def test_creation_star_state_tracks_steps() -> None:
    state = build_creation_star_state(project_id="prj_test", current_step="worldview")
    assert isinstance(state, CreationStarState)
    assert state.project_id == "prj_test"
    assert state.current_step == "worldview"
    assert state.confirmed is False
