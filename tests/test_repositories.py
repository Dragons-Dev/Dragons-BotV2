from datetime import date, datetime, timedelta
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import discord
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import SERVER_TZ
from extensions.administration.models import BotStatus
from extensions.administration.repository import BotStatusRepository
from extensions.automation.repository import Join2CreateRepository
from extensions.fun.repository import EventRepository
from extensions.internal.repository import EnabledCommandsRepository
from extensions.moderation.models import Infractions
from extensions.moderation.repository import InfractionsRepository, ModmailRepository
from extensions.stats.repository import UserStatsRepository
from utils.enums import InfractionsEnum, SettingsEnum, StatTypeEnum
from utils.orm_database import Base, ORMDataBase, SettingsRepository

EXPECTED_TABLES = {
    "Confirmation",
    "Events",
    "botstatus",
    "enabledcommands",
    "infractions",
    "join2create",
    "migration_history",
    "modmail",
    "settings",
    "userstats",
}


def mock_entity(entity_id: int) -> SimpleNamespace:
    return SimpleNamespace(id=entity_id)


class TestRepositories(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.session_maker: async_sessionmaker[AsyncSession] = async_sessionmaker(self.engine, expire_on_commit=False)
        # Ensure all models are discovered and tables created
        ORMDataBase._discover_models(SimpleNamespace(logger=None))  # type: ignore[arg-type]
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_discover_models_registers_all_tables_regardless_of_cwd(self):
        orig_cwd = os.getcwd()
        parent_dir = Path(orig_cwd).parent
        try:
            os.chdir(parent_dir)
            ORMDataBase._discover_models(SimpleNamespace(logger=None))  # type: ignore[arg-type]
            registered_tables = set(Base.metadata.tables.keys())
            self.assertEqual(registered_tables, EXPECTED_TABLES)
        finally:
            os.chdir(orig_cwd)

    async def test_settings_repository(self):
        settings_repo = SettingsRepository(self.session_maker)
        guild_a = mock_entity(1001)
        guild_b = mock_entity(1002)

        # Initially None
        self.assertIsNone(await settings_repo.get_setting(SettingsEnum.TeamRole, guild_a))  # type: ignore[arg-type]
        self.assertIsNone(await settings_repo.get_all_settings(SettingsEnum.TeamRole))

        # Insert via update_setting
        await settings_repo.update_setting(SettingsEnum.TeamRole, 555, guild_a)  # type: ignore[arg-type]
        setting_a = await settings_repo.get_setting(SettingsEnum.TeamRole, guild_a)  # type: ignore[arg-type]
        self.assertIsNotNone(setting_a)
        self.assertEqual(setting_a.value, 555)
        self.assertEqual(setting_a.guild, 1001)

        # Update existing setting
        await settings_repo.update_setting(SettingsEnum.TeamRole, 777, guild_a)  # type: ignore[arg-type]
        setting_a_updated = await settings_repo.get_setting(SettingsEnum.TeamRole, guild_a)  # type: ignore[arg-type]
        self.assertIsNotNone(setting_a_updated)
        self.assertEqual(setting_a_updated.value, 777)

        # Add second guild setting and test get_all_settings
        await settings_repo.update_setting(SettingsEnum.TeamRole, 888, guild_b)  # type: ignore[arg-type]
        all_settings = await settings_repo.get_all_settings(SettingsEnum.TeamRole)
        self.assertIsNotNone(all_settings)
        self.assertEqual(len(all_settings), 2)

        # Delete setting (including non-existing safe no-op)
        await settings_repo.delete_setting(SettingsEnum.TeamRole, guild_a)  # type: ignore[arg-type]
        self.assertIsNone(await settings_repo.get_setting(SettingsEnum.TeamRole, guild_a))  # type: ignore[arg-type]
        await settings_repo.delete_setting(SettingsEnum.TeamRole, guild_a)  # type: ignore[arg-type]

    async def test_bot_status_repository(self):
        status_repo = BotStatusRepository(self.session_maker)

        # Initially empty -> None
        self.assertIsNone(await status_repo.get_bot_status(None))

        # Create first status
        await status_repo.create_bot_status(discord.ActivityType.watching, discord.Status.online, "Dragons Server")
        status_single = await status_repo.get_bot_status(None)
        self.assertIsInstance(status_single, BotStatus)
        self.assertEqual(status_single.activity_name, "Dragons Server")
        self.assertEqual(status_single.activity_type, int(discord.ActivityType.watching))
        self.assertEqual(status_single.status, str(discord.Status.online))

        # Partial edit (None vs non-None, including ActivityType.playing which has int value 0)
        await status_repo.edit_bot_status(
            status_single.id,
            activity_type=discord.ActivityType.playing,
            status=None,
            activity_name=None,
        )
        edited = await status_repo.get_bot_status(status_single.id)
        self.assertIsInstance(edited, BotStatus)
        self.assertEqual(edited.activity_type, int(discord.ActivityType.playing))
        self.assertEqual(edited.status, str(discord.Status.online))
        self.assertEqual(edited.activity_name, "Dragons Server")

        # Partial edit of status and activity_name
        await status_repo.edit_bot_status(
            status_single.id,
            activity_type=None,
            status=discord.Status.dnd,
            activity_name="Maintenance",
        )
        edited_2 = await status_repo.get_bot_status(status_single.id)
        self.assertIsInstance(edited_2, BotStatus)
        self.assertEqual(edited_2.activity_type, int(discord.ActivityType.playing))
        self.assertEqual(edited_2.status, str(discord.Status.dnd))
        self.assertEqual(edited_2.activity_name, "Maintenance")

        # Create second status -> get_bot_status(None) returns sequence
        await status_repo.create_bot_status(discord.ActivityType.listening, discord.Status.idle, "Music")
        all_statuses = await status_repo.get_bot_status(None)
        self.assertIsInstance(all_statuses, list)
        self.assertEqual(len(all_statuses), 2)

        # Delete statuses & verify safe handling of missing id
        await status_repo.delete_bot_status(status_single.id)
        await status_repo.delete_bot_status(99999)
        remaining = await status_repo.get_bot_status(None)
        self.assertIsInstance(remaining, BotStatus)
        self.assertEqual(remaining.activity_name, "Music")

    async def test_join2create_repository(self):
        join2create_repo = Join2CreateRepository(self.session_maker)
        channel = mock_entity(2001)
        derived = mock_entity(2000)
        owner_1 = mock_entity(3001)
        owner_2 = mock_entity(3002)
        missing_channel = mock_entity(9999)

        # Safe handling when row does not exist
        self.assertIsNone(await join2create_repo.get(missing_channel))  # type: ignore[arg-type]
        await join2create_repo.update(missing_channel, owner_1)  # type: ignore[arg-type]
        await join2create_repo.delete(missing_channel)  # type: ignore[arg-type]

        # Create
        created = await join2create_repo.create(channel, owner_1, derived)  # type: ignore[arg-type]
        self.assertIsNotNone(created)
        self.assertEqual(created.channel, 2001)
        self.assertEqual(created.owner_id, 3001)
        self.assertEqual(created.derived_channel, 2000)

        # Get
        fetched = await join2create_repo.get(channel)  # type: ignore[arg-type]
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.owner_id, 3001)

        # Update owner
        await join2create_repo.update(channel, owner_2)  # type: ignore[arg-type]
        updated = await join2create_repo.get(channel)  # type: ignore[arg-type]
        self.assertIsNotNone(updated)
        self.assertEqual(updated.owner_id, 3002)

        # Delete
        await join2create_repo.delete(channel)  # type: ignore[arg-type]
        self.assertIsNone(await join2create_repo.get(channel))  # type: ignore[arg-type]

    async def test_enabled_commands_repository(self):
        enabled_commands_repo = EnabledCommandsRepository(self.session_maker)
        guild = mock_entity(4001)

        # Default is True when no row exists
        self.assertTrue(await enabled_commands_repo.is_command_enabled(guild, "mod ban"))  # type: ignore[arg-type]

        # First toggle disables the command
        state_1 = await enabled_commands_repo.toggle_command(guild, "mod ban")  # type: ignore[arg-type]
        self.assertFalse(state_1)
        self.assertFalse(await enabled_commands_repo.is_command_enabled(guild, "mod ban"))  # type: ignore[arg-type]

        # Second toggle re-enables the command
        state_2 = await enabled_commands_repo.toggle_command(guild, "mod ban")  # type: ignore[arg-type]
        self.assertTrue(state_2)
        self.assertTrue(await enabled_commands_repo.is_command_enabled(guild, "mod ban"))  # type: ignore[arg-type]

    async def test_infractions_repository_and_guild_isolation(self):
        infractions_repo = InfractionsRepository(self.session_maker)
        user = mock_entity(5001)
        guild_a = mock_entity(6001)
        guild_b = mock_entity(6002)

        # LookupError when both case_id and user are None
        with self.assertRaises(LookupError):
            await infractions_repo.get_infraction(None, None)

        # Create infraction in guild A
        case_a1 = await infractions_repo.create_infraction(user, InfractionsEnum.Warn, "Spamming", guild_a)  # type: ignore[arg-type]
        self.assertIsInstance(case_a1, int)

        # Retrieve by case_id
        inf_by_case = await infractions_repo.get_infraction(case_a1, None)
        self.assertIsInstance(inf_by_case, Infractions)
        self.assertEqual(inf_by_case.reason, "Spamming")
        self.assertEqual(inf_by_case.guild, 6001)

        # Issue #2 fix verification: querying for user in guild B must NOT return guild A infractions
        self.assertIsNone(await infractions_repo.get_infraction(None, user, guild_b))  # type: ignore[arg-type]

        # Querying for user in guild A returns the infraction
        inf_guild_a = await infractions_repo.get_infraction(None, user, guild_a)  # type: ignore[arg-type]
        self.assertIsInstance(inf_guild_a, Infractions)
        self.assertEqual(inf_guild_a.case_id, case_a1)

        # Create a second infraction in guild A and one in guild B
        case_a2 = await infractions_repo.create_infraction(user, InfractionsEnum.Timeout, "Flood", guild_a)  # type: ignore[arg-type]
        case_b1 = await infractions_repo.create_infraction(user, InfractionsEnum.Kick, "Rule 1", guild_b)  # type: ignore[arg-type]

        infs_a = await infractions_repo.get_infraction(None, user, guild_a)  # type: ignore[arg-type]
        self.assertIsInstance(infs_a, list)
        self.assertEqual({i.case_id for i in infs_a}, {case_a1, case_a2})

        inf_b = await infractions_repo.get_infraction(None, user, guild_b)  # type: ignore[arg-type]
        self.assertIsInstance(inf_b, Infractions)
        self.assertEqual(inf_b.case_id, case_b1)

    async def test_modmail_repository(self):
        modmail_repo = ModmailRepository(self.session_maker)
        user = mock_entity(7001)
        guild = mock_entity(8001)
        uuid_str = "12345678-1234-5678-1234-567812345678"

        with self.assertRaises(LookupError):
            await modmail_repo.get_modmail(None, None)

        # Not found returns None
        self.assertIsNone(await modmail_repo.get_modmail(user, None))  # type: ignore[arg-type]
        self.assertIsNone(await modmail_repo.get_modmail(None, uuid_str))

        # Create modmail
        await modmail_repo.create_modmail(user, guild, uuid_str, anonymous=True)  # type: ignore[arg-type]

        # Get by user and by uuid
        by_user = await modmail_repo.get_modmail(user, None)  # type: ignore[arg-type]
        self.assertIsNotNone(by_user)
        self.assertEqual(by_user.uuid, uuid_str)
        self.assertEqual(by_user.guild_id, 8001)
        self.assertTrue(by_user.anon)

        by_uuid = await modmail_repo.get_modmail(None, uuid_str)
        self.assertIsNotNone(by_uuid)
        self.assertEqual(by_uuid.user_id, 7001)

        # Delete modmail (and safe delete when already absent)
        await modmail_repo.delete_modmail(user)  # type: ignore[arg-type]
        self.assertIsNone(await modmail_repo.get_modmail(user, None))  # type: ignore[arg-type]
        await modmail_repo.delete_modmail(user)  # type: ignore[arg-type]

    async def test_user_stats_repository_and_multi_day_handling(self):
        user_stats_repo = UserStatsRepository(self.session_maker)
        user = mock_entity(9001)
        guild = mock_entity(9501)

        day_1 = date.today() - timedelta(days=2)
        day_2 = date.today()

        # Simulate updates on day_1
        with patch("extensions.stats.repository.date") as mock_date:
            mock_date.today.return_value = day_1
            await user_stats_repo.update_user_stat(user, StatTypeEnum.MessagesSent, 3, guild)  # type: ignore[arg-type]
            await user_stats_repo.update_user_stat(user, StatTypeEnum.MessagesSent, 2, guild)  # type: ignore[arg-type]

        # Simulate updates on day_2 (Issue #1 fix: must create a separate row and not raise MultipleResultsFound)
        with patch("extensions.stats.repository.date") as mock_date:
            mock_date.today.return_value = day_2
            await user_stats_repo.update_user_stat(user, StatTypeEnum.MessagesSent, 4, guild)  # type: ignore[arg-type]
            await user_stats_repo.update_user_stat(user, StatTypeEnum.MessagesSent, 6, guild)  # type: ignore[arg-type]

        # Verify get_user_stat_days returns 2 distinct day rows
        stat_days = await user_stats_repo.get_user_stat_days(user, StatTypeEnum.MessagesSent, guild, days_back=5)  # type: ignore[arg-type]
        self.assertEqual(len(stat_days), 2)
        day_map = {row.day: row.value for row in stat_days}
        self.assertEqual(day_map[day_1], 5)
        self.assertEqual(day_map[day_2], 10)

        # Verify get_user_stat_total sums across all days
        total = await user_stats_repo.get_user_stat_total(user, StatTypeEnum.MessagesSent, guild)  # type: ignore[arg-type]
        self.assertEqual(total, 15)

        # Verify delete_user_stats (no-op when both None, then actual delete)
        await user_stats_repo.delete_user_stats(None, StatTypeEnum.MessagesSent, None)
        self.assertEqual(await user_stats_repo.get_user_stat_total(user, StatTypeEnum.MessagesSent, guild), 15)  # type: ignore[arg-type]

        await user_stats_repo.delete_user_stats(user, StatTypeEnum.MessagesSent, guild)  # type: ignore[arg-type]
        self.assertEqual(await user_stats_repo.get_user_stat_total(user, StatTypeEnum.MessagesSent, guild), 0)  # type: ignore[arg-type]
        self.assertEqual(
            len(await user_stats_repo.get_user_stat_days(user, StatTypeEnum.MessagesSent, guild, days_back=5)), 0
        )  # type: ignore[arg-type]

    async def test_event_repository(self):
        event_repo = EventRepository(self.session_maker)
        guest_1 = mock_entity(1101)
        guest_2 = mock_entity(1102)
        guest_3 = mock_entity(1103)
        event_time = datetime.now(tz=SERVER_TZ) + timedelta(days=1)

        # Atomically create event + initial confirmations
        event_id = await event_repo.create_event(
            host=1000,
            name="Dragon Raid",
            time=event_time,
            invites=[guest_1, guest_2],  # type: ignore[list-item]
            mode="OPEN",
        )
        self.assertTrue(event_id.startswith("1000"))

        # All invited users are recorded
        all_invited = await event_repo.get_all_confirmations_for_event(event_id=event_id)
        self.assertEqual(set(all_invited), {1101, 1102})

        # Initially no one has accepted (confirmation is None)
        self.assertEqual(await event_repo.get_confirmations_for_event(event_id=event_id), [])
        self.assertEqual(await event_repo.get_complete_confirmations_for_event(event_id=event_id), [])

        # Add a third guest confirmation directly
        await event_repo.create_confirmation(event_id=event_id, guest=guest_3.id, confirmation=None, reminders=[0])
        self.assertEqual(set(await event_repo.get_all_confirmations_for_event(event_id=event_id)), {1101, 1102, 1103})

        # Update confirmations: guest_1 accepts with reminders, guest_2 declines
        self.assertTrue(
            await event_repo.update_confirmation(
                event_id=event_id, guest=guest_1.id, confirmation=True, reminders=[0, 60, 600]
            )
        )
        self.assertTrue(
            await event_repo.update_confirmation(event_id=event_id, guest=guest_2.id, confirmation=False, reminders=[0])
        )
        # Updating non-existent confirmation returns False
        self.assertFalse(
            await event_repo.update_confirmation(event_id=event_id, guest=9999, confirmation=True, reminders=[0])
        )

        # Verify get_confirmation_for_event_and_user
        conf_1 = await event_repo.get_confirmation_for_event_and_user(event_id=event_id, guest=guest_1.id)
        self.assertIsNotNone(conf_1)
        self.assertTrue(conf_1.confirmation)
        self.assertEqual(conf_1.reminders, [0, 60, 600])
        self.assertIsNone(await event_repo.get_confirmation_for_event_and_user(event_id=event_id, guest=9999))

        # Verify accepted confirmations queries
        accepted_ids = await event_repo.get_confirmations_for_event(event_id=event_id)
        self.assertEqual(accepted_ids, [1101])

        complete_confs = await event_repo.get_complete_confirmations_for_event(event_id=event_id)
        self.assertEqual(len(complete_confs), 1)
        self.assertEqual(complete_confs[0].guest, 1101)
        self.assertEqual(complete_confs[0].reminders, [0, 60, 600])

        # Verify get_event_by_id & get_events
        fetched_event = await event_repo.get_event_by_id(event_id)
        self.assertIsNotNone(fetched_event)
        self.assertEqual(fetched_event.name, "Dragon Raid")
        self.assertEqual(fetched_event.invites, [1101])

        all_events = await event_repo.get_events()
        self.assertEqual(len(all_events), 1)
        self.assertEqual(all_events[0].id, event_id)

        # Verify update_event
        self.assertTrue(await event_repo.update_event(id=event_id, name="Mythic Dragon Raid", mode="CLOSED"))
        self.assertFalse(await event_repo.update_event(id="non-existent-id", name="Nope"))
        updated_event = await event_repo.get_event_by_id(event_id)
        self.assertIsNotNone(updated_event)
        self.assertEqual(updated_event.name, "Mythic Dragon Raid")
        self.assertEqual(updated_event.mode, "CLOSED")

        # Verify delete_event atomically removes both confirmations and event
        self.assertTrue(await event_repo.delete_event(event_id))
        self.assertIsNone(await event_repo.get_event_by_id(event_id))
        self.assertEqual(await event_repo.get_all_confirmations_for_event(event_id=event_id), [])


if __name__ == "__main__":
    unittest.main()
