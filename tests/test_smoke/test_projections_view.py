"""UI smoke test for the Projections view — the most complex view, not
covered by the basic nav-page smoke tests.
"""
from __future__ import annotations

import pytest

from config.settings import settings
from db.connection import Database
from db.migrate import run_migrations
from models.goal import Goal
from models.holding import Holding
from services.app_context import AppContext
from services.data_loader import DataLoader
from tests.conftest import SCHEMA_PATH

pytestmark = pytest.mark.smoke


@pytest.fixture
def seeded_ctx(tmp_path, empty_store) -> AppContext:
    database = Database()
    database.connect(tmp_path / "projections_smoke.db")
    database.apply_schema(SCHEMA_PATH)
    run_migrations(database)

    loader = DataLoader(database)
    loader.load_seed_data(settings.SEED_DIR)
    loader.load_store_data(empty_store)

    ctx = AppContext.create(database)

    # A SIP holding linked to a goal with a target date, so both the
    # net-worth tile and a goal tile are populated.
    holding_id = ctx.investment_service.add_holding(
        Holding(name="Retirement SIP", holding_type="sip",
                invested_amount=100_000.0, current_value=120_000.0,
                sip_amount=10_000.0)
    )
    ctx.goal_service.create(
        Goal(name="Retirement", target_amount=5_000_000.0, current_amount=0.0,
             target_date="2045-01-01", expected_return=0.10),
        holding_ids=[holding_id],
    )

    yield ctx
    database.close()


def test_projections_view_renders_with_data(qtbot, seeded_ctx):
    from ui.views.projections_view import ProjectionsView

    view = ProjectionsView(seeded_ctx)
    qtbot.addWidget(view)

    # Net-worth tile + the linked goal's tile should both be present.
    assert len(view._tiles) >= 2
    keys = {t.key for t in view._tiles}
    assert "networth" in keys
    assert any(k.startswith("goal:") for k in keys)

    # Detail pane should switch away from the placeholder once tiles exist.
    assert view.detail_stack.currentIndex() == 1


def test_projections_view_goal_tile_detail(qtbot, seeded_ctx):
    from ui.views.projections_view import ProjectionsView

    view = ProjectionsView(seeded_ctx)
    qtbot.addWidget(view)

    goal_key = next(t.key for t in view._tiles if t.key.startswith("goal:"))
    view._on_tile_clicked(goal_key)

    assert view._selected_key == goal_key
    assert view.detail_layout.count() > 0
