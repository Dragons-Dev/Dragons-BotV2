import importlib
import pkgutil
from datetime import datetime
from pathlib import Path
from types import ModuleType

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncEngine

from utils.logger import CustomLogger
from utils.orm_database.models import MigrationHistory
from utils.utils import VersionInfo

__all__ = ["run_migrations"]


def _discover_pending_migrations(
    applied: set[str], bot_version: VersionInfo
) -> list[tuple[VersionInfo, str, ModuleType]]:
    migrations_dir = str(Path(__file__).parent)
    pending: list[tuple[VersionInfo, str, ModuleType]] = []

    for module_info in pkgutil.iter_modules([migrations_dir]):
        name = module_info.name
        if name.startswith("_") or name in applied:
            continue

        module = importlib.import_module(f"{__name__}.{name}")
        target_version: VersionInfo | None = getattr(module, "TARGET_VERSION", None)
        migrate_fn = getattr(module, "migrate", None)

        if isinstance(target_version, VersionInfo) and callable(migrate_fn) and target_version <= bot_version:
            pending.append((target_version, name, module))

    pending.sort(key=lambda item: item[0])
    return pending


async def run_migrations(engine: AsyncEngine, boot: datetime, bot_version: VersionInfo) -> None:
    """
    Discovers and runs all pending database migrations whose TARGET_VERSION <= bot_version.
    Each applied migration is recorded in the migration_history table so it only runs once.
    """
    logger = CustomLogger("migrations", boot)
    async with engine.begin() as conn:
        await conn.run_sync(MigrationHistory.__table__.create, checkfirst=True)
        result = await conn.execute(select(MigrationHistory.script_name))
        applied = set(result.scalars().all())

        pending = _discover_pending_migrations(applied, bot_version)
        for target_version, script_name, module in pending:
            logger.info(f"Running migration '{script_name}' (target version {target_version})...")
            await module.migrate(conn)
            await conn.execute(
                insert(MigrationHistory).values(
                    script_name=script_name,
                    version=str(target_version),
                    applied_at=datetime.now(),
                )
            )
            logger.info(f"Successfully applied migration '{script_name}'.")
