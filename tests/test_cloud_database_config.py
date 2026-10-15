
"""Blue Moon Apartments cloud database safety tests."""

from types import SimpleNamespace

import pytest

from sqlalchemy import create_engine, inspect

from database import db as db_module
from database.models import Base


def test_development_database_still_initializes(
    monkeypatch,
):
    """Local development must retain table creation."""

    engine = create_engine(
        "sqlite+pysqlite:///:memory:"
    )

    try:

        monkeypatch.setattr(
            db_module,
            "engine",
            engine,
        )

        monkeypatch.setattr(
            db_module,
            "IS_PRODUCTION",
            False,
        )

        db_module.init_db()

        tables = inspect(
            engine
        ).get_table_names()

        assert set(tables) == set(
            Base.metadata.tables.keys()
        )

    finally:
        engine.dispose()


def test_production_rejects_missing_schema(
    monkeypatch,
):
    """Production must not create missing tables."""

    monkeypatch.setattr(
        db_module,
        "IS_PRODUCTION",
        True,
    )

    monkeypatch.setattr(
        db_module,
        "inspect",
        lambda engine: SimpleNamespace(
            get_table_names=lambda **kwargs: []
        ),
    )

    def reject_creation(*args, **kwargs):
        pytest.fail(
            "Production attempted automatic schema creation."
        )

    monkeypatch.setattr(
        Base.metadata,
        "create_all",
        reject_creation,
    )

    with pytest.raises(
        RuntimeError,
        match="missing",
    ):
        db_module.init_db()


def test_production_accepts_existing_schema(
    monkeypatch,
):
    """Existing production schema needs no DDL."""

    expected_tables = list(
        Base.metadata.tables.keys()
    )

    monkeypatch.setattr(
        db_module,
        "IS_PRODUCTION",
        True,
    )

    monkeypatch.setattr(
        db_module,
        "inspect",
        lambda engine: SimpleNamespace(
            get_table_names=(
                lambda **kwargs: expected_tables
            )
        ),
    )

    def reject_creation(*args, **kwargs):
        pytest.fail(
            "Production attempted automatic schema creation."
        )

    monkeypatch.setattr(
        Base.metadata,
        "create_all",
        reject_creation,
    )

    db_module.init_db()
