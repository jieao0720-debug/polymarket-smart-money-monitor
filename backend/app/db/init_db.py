# Import models so that Base.metadata is fully populated before create_all.
from sqlalchemy import inspect
from sqlalchemy.engine import Connection

from app import models  # noqa: F401
from app.db.base import Base
from app.db.session import get_engine


def add_missing_nullable_columns(conn: Connection) -> list[str]:
    """Minimal additive migration (no Alembic, A10): create_all never alters existing
    tables, so nullable columns added to a model later are appended here. Only
    nullable columns are handled — anything else needs a real migration."""
    inspector = inspect(conn)
    existing_tables = set(inspector.get_table_names())
    added: list[str] = []
    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        present = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in present or not column.nullable:
                continue
            col_type = column.type.compile(dialect=conn.dialect)
            conn.exec_driver_sql(
                f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}')
            added.append(f"{table.name}.{column.name}")
    return added


async def init_db() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(add_missing_nullable_columns)
