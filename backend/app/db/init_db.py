# Import models so that Base.metadata is fully populated before create_all.
from app import models  # noqa: F401
from app.db.base import Base
from app.db.session import get_engine


async def init_db() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
