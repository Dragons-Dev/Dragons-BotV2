from datetime import datetime, timedelta
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from extensions.moderation.bad_urls import SafebrowsingCog
from extensions.moderation.ban import Ban
from extensions.moderation.kick import Kick
from extensions.moderation.models import Infractions
from extensions.moderation.moderation_events import ModerationEvents, ModerationQuickTicketView
from extensions.moderation.repository import InfractionsRepository
from extensions.moderation.timeout import Timeout, _parse_duration  # type: ignore[attr-defined]
from extensions.moderation.warn import Warn
from utils import InfractionsEnum, ModerationEnum
from utils.orm_database import Base, ORMDataBase


def create_mock_member(user_id: int = 12345, name: str = "TestUser", top_role_pos: int = 1) -> MagicMock:
    member = MagicMock(spec=discord.Member)
    member.id = user_id
    member.name = name
    member.display_name = name
    member.mention = f"<@{user_id}>"
    member.bot = False
    member.top_role = MagicMock()
    member.top_role.__ge__ = lambda self, other: top_role_pos >= getattr(other, "position", 0)
    member.top_role.__lt__ = lambda self, other: top_role_pos < getattr(other, "position", 0)
    member.top_role.position = top_role_pos
    member.send = AsyncMock()
    member.kick = AsyncMock()
    member.timeout_for = AsyncMock()
    member.display_avatar = MagicMock()
    member.display_avatar.url = "https://example.com/avatar.png"
    return member


def create_mock_guild(guild_id: int = 99999, bot_top_role_pos: int = 10) -> MagicMock:
    guild = MagicMock(spec=discord.Guild)
    guild.id = guild_id
    guild.ban = AsyncMock()
    guild.kick = AsyncMock()
    guild.get_or_fetch = AsyncMock()

    bot_member = MagicMock(spec=discord.Member)
    bot_member.top_role = MagicMock()
    bot_member.top_role.position = bot_top_role_pos
    bot_member.top_role.__ge__ = lambda self, other: bot_top_role_pos >= getattr(other, "position", 0)
    guild.me = bot_member
    return guild


def create_mock_context(guild: MagicMock, author: MagicMock) -> MagicMock:
    ctx = MagicMock(spec=discord.ApplicationContext)
    ctx.guild = guild
    ctx.author = author
    ctx.response = MagicMock()
    ctx.response.is_done = MagicMock(return_value=False)
    ctx.response.send_message = AsyncMock()
    ctx.followup = MagicMock()
    ctx.followup.send = AsyncMock()
    return ctx


class TestModerationEvents(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.session_maker: async_sessionmaker[AsyncSession] = async_sessionmaker(self.engine, expire_on_commit=False)
        ORMDataBase._discover_models(SimpleNamespace(logger=None))  # type: ignore[arg-type]
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        self.infractions_repo = InfractionsRepository(self.session_maker)
        self.mock_client = MagicMock()
        self.mock_client.boot_time = datetime.now()
        self.mock_client.db = MagicMock()
        self.mock_client.db.session_maker = self.session_maker
        self.mock_client.db.get_setting = AsyncMock(return_value=None)
        self.cog = ModerationEvents(self.mock_client, infractions_repo=self.infractions_repo)

        self.guild = create_mock_guild()
        self.member = create_mock_member(user_id=101, name="TargetMember")
        self.moderator = create_mock_member(user_id=202, name="ModUser")
        self.log_channel = MagicMock(spec=discord.TextChannel)
        self.log_channel.send = AsyncMock()

    async def asyncTearDown(self):
        await self.engine.dispose()

    def test_enums(self):
        self.assertIs(ModerationEnum, InfractionsEnum)
        self.assertEqual(ModerationEnum.Ban, InfractionsEnum.Ban)
        self.assertEqual(ModerationEnum.Kick, InfractionsEnum.Kick)
        self.assertEqual(ModerationEnum.Timeout, InfractionsEnum.Timeout)
        self.assertEqual(ModerationEnum.Warn, InfractionsEnum.Warn)

    async def test_on_moderation_action_ban(self):
        setting_mock = MagicMock()
        setting_mock.value = 55555
        self.mock_client.db.get_setting.return_value = setting_mock
        self.guild.get_or_fetch.return_value = self.log_channel

        ctx = create_mock_context(self.guild, self.moderator)
        ctx.response.is_done.return_value = True

        case_id = await self.cog.on_moderation_action(
            InfractionsEnum.Ban,
            self.member,
            self.guild,
            "Violating rules",
            self.moderator,
            ctx=ctx,
        )

        self.assertIsInstance(case_id, int)
        # 1. Action executed
        self.guild.ban.assert_awaited_once_with(self.member, reason="Violating rules")
        # 2. DB infraction created
        db_record = await self.infractions_repo.get_infraction(case_id=case_id, user=None)
        self.assertIsNotNone(db_record)
        assert isinstance(db_record, Infractions)
        self.assertEqual(db_record.user_id, self.member.id)
        self.assertEqual(db_record.infraction, "Ban")
        self.assertEqual(db_record.reason, "Violating rules")

        # 4. DM sent
        self.member.send.assert_awaited_once()
        dm_call_kwargs = self.member.send.call_args.kwargs
        dm_embed = dm_call_kwargs.get("embed")
        self.assertIsNotNone(dm_embed)
        self.assertEqual(dm_embed.title, "Ban")
        self.assertEqual(dm_embed.color, discord.Color.brand_red())
        self.assertIn(f"Case ID: {case_id}", dm_embed.footer.text)
        dm_view = dm_call_kwargs.get("view")
        self.assertIsInstance(dm_view, ModerationQuickTicketView)

        # 5. Log channel sent
        self.log_channel.send.assert_awaited_once()
        log_embed = self.log_channel.send.call_args.kwargs.get("embed")
        self.assertEqual(log_embed.title, "Ban")

        # 6. Moderator feedback via followup (since is_done=True)
        ctx.followup.send.assert_awaited_once()
        mod_call_kwargs = ctx.followup.send.call_args.kwargs
        mod_embed = mod_call_kwargs.get("embed")
        self.assertIsNotNone(mod_embed)
        self.assertEqual(mod_embed.title, "Ban successful")
        self.assertEqual(mod_embed.color, discord.Color.brand_green())
        mod_view = mod_call_kwargs.get("view")
        self.assertIsNotNone(mod_view)
        # Verify past-tense mapping: "banned" instead of "baned"
        self.assertIn("banned", mod_view.children[0].label)

    async def test_on_moderation_action_order_dm_before_ban_and_kick(self):
        call_order = []

        async def mock_send(*args, **kwargs):
            call_order.append("send")

        async def mock_ban(*args, **kwargs):
            call_order.append("ban")

        async def mock_kick(*args, **kwargs):
            call_order.append("kick")

        self.member.send.side_effect = mock_send
        self.guild.ban.side_effect = mock_ban
        self.member.kick.side_effect = mock_kick

        # Verify Ban order: DM must happen BEFORE guild.ban
        call_order.clear()
        await self.cog.on_moderation_action(
            InfractionsEnum.Ban,
            self.member,
            self.guild,
            "Ban order check",
            self.moderator,
        )
        self.assertEqual(call_order, ["send", "ban"])

        # Verify Kick order: DM must happen BEFORE member.kick
        call_order.clear()
        await self.cog.on_moderation_action(
            InfractionsEnum.Kick,
            self.member,
            self.guild,
            "Kick order check",
            self.moderator,
        )
        self.assertEqual(call_order, ["send", "kick"])

        # Verify Timeout order: member.timeout_for must happen BEFORE DM
        async def mock_timeout(*args, **kwargs):
            call_order.append("timeout")

        self.member.timeout_for.side_effect = mock_timeout
        call_order.clear()
        await self.cog.on_moderation_action(
            InfractionsEnum.Timeout,
            self.member,
            self.guild,
            "Timeout order check",
            self.moderator,
            duration=timedelta(minutes=5),
        )
        self.assertEqual(call_order, ["timeout", "send"])

    async def test_on_moderation_action_discord_action_forbidden_handled(self):
        self.guild.ban.side_effect = discord.Forbidden(MagicMock(), "Missing Permissions")
        ctx = create_mock_context(self.guild, self.moderator)
        ctx.response.is_done.return_value = True

        result = await self.cog.on_moderation_action(
            InfractionsEnum.Ban,
            self.member,
            self.guild,
            "Ban permission failure",
            self.moderator,
            ctx=ctx,
        )
        self.assertIsNone(result)
        # ModLogChannel should NOT be sent when discord action fails
        self.log_channel.send.assert_not_called()
        # Moderator receives error feedback
        ctx.followup.send.assert_awaited_once()
        err_embed = ctx.followup.send.call_args.kwargs.get("embed")
        self.assertIsNotNone(err_embed)
        self.assertEqual(err_embed.title, "Failed to ban user")
        self.assertEqual(err_embed.color, discord.Color.brand_red())

    async def test_on_moderation_action_timeout_forbidden_handled(self):
        self.member.timeout_for.side_effect = discord.Forbidden(MagicMock(), "Missing Permissions")
        ctx = create_mock_context(self.guild, self.moderator)
        ctx.response.is_done.return_value = False

        result = await self.cog.on_moderation_action(
            InfractionsEnum.Timeout,
            self.member,
            self.guild,
            "Timeout permission failure",
            self.moderator,
            duration=timedelta(minutes=5),
            ctx=ctx,
        )
        self.assertIsNone(result)
        self.log_channel.send.assert_not_called()
        self.member.send.assert_not_called()
        ctx.response.send_message.assert_awaited_once()
        err_embed = ctx.response.send_message.call_args.kwargs.get("embed")
        self.assertIsNotNone(err_embed)
        self.assertEqual(err_embed.title, "Failed to timeout user")
        self.assertEqual(err_embed.color, discord.Color.brand_red())

    async def test_on_moderation_action_mod_log_failure_does_not_abort_feedback(self):
        setting_mock = MagicMock()
        setting_mock.value = 55555
        self.mock_client.db.get_setting.return_value = setting_mock
        self.guild.get_or_fetch.return_value = self.log_channel
        self.log_channel.send.side_effect = discord.Forbidden(MagicMock(), "Missing Permissions")

        ctx = create_mock_context(self.guild, self.moderator)
        ctx.response.is_done.return_value = True

        case_id = await self.cog.on_moderation_action(
            InfractionsEnum.Ban,
            self.member,
            self.guild,
            "Log error check",
            self.moderator,
            ctx=ctx,
        )
        self.assertIsInstance(case_id, int)
        ctx.followup.send.assert_awaited_once()

    async def test_on_moderation_action_kick_with_channel_sequence(self):
        setting_mock = MagicMock()
        setting_mock.value = 66666
        self.mock_client.db.get_setting.return_value = [setting_mock]
        self.guild.get_or_fetch.return_value = self.log_channel

        ctx = create_mock_context(self.guild, self.moderator)
        ctx.response.is_done.return_value = False

        case_id = await self.cog.on_moderation_action(
            InfractionsEnum.Kick,
            self.member,
            self.guild,
            "Spamming",
            self.moderator,
            ctx=ctx,
        )

        self.assertIsInstance(case_id, int)
        self.member.kick.assert_awaited_once_with(reason="Spamming")
        self.log_channel.send.assert_awaited_once()
        # With is_done=False, should call response.send_message
        ctx.response.send_message.assert_awaited_once()
        mod_embed = ctx.response.send_message.call_args.kwargs.get("embed")
        self.assertEqual(mod_embed.title, "Kick successful")

    async def test_on_moderation_action_timeout(self):
        duration = timedelta(minutes=10)
        case_id = await self.cog.on_moderation_action(
            InfractionsEnum.Timeout,
            self.member,
            self.guild,
            "Excessive caps",
            self.moderator,
            duration=duration,
        )

        self.assertIsInstance(case_id, int)
        self.member.timeout_for.assert_awaited_once_with(duration=duration, reason="Excessive caps")
        self.member.send.assert_awaited_once()
        dm_embed = self.member.send.call_args.kwargs.get("embed")
        self.assertEqual(dm_embed.title, "Timeout")
        self.assertEqual(dm_embed.color, discord.Color.yellow())
        field_names = [f.name for f in dm_embed.fields]
        self.assertIn("Until", field_names)

    async def test_on_moderation_action_warn_safebrowsing_custom_kwargs(self):
        link_bed = discord.Embed(title="Message context", description="Malicious link")
        case_id = await self.cog.on_moderation_action(
            InfractionsEnum.Warn,
            self.member,
            self.guild,
            "Bad URL sent",
            self.moderator,
            log_reason="Sending a malicious link",
            embed_title="Message delete",
            extra_embeds=[link_bed],
            dm_info_text="You were warned due to the message above.",
        )

        self.assertIsInstance(case_id, int)
        # Check DB recorded reason
        db_record = await self.infractions_repo.get_infraction(case_id=case_id, user=None)
        assert isinstance(db_record, Infractions)
        self.assertEqual(db_record.reason, "Bad URL sent")

        # Check DM with extra_embeds and custom title/reason
        self.member.send.assert_awaited_once()
        call_kwargs = self.member.send.call_args.kwargs
        self.assertIn("embeds", call_kwargs)
        embeds = call_kwargs["embeds"]
        self.assertEqual(len(embeds), 2)
        self.assertEqual(embeds[0].title, "Message delete")
        reason_field = next(f for f in embeds[0].fields if f.name == "Reason")
        self.assertEqual(reason_field.value, "Sending a malicious link")
        self.assertEqual(embeds[1], link_bed)
        self.assertIn("view", call_kwargs)
        self.assertIsInstance(call_kwargs["view"], ModerationQuickTicketView)
        self.assertEqual(call_kwargs["view"].info_text, "You were warned due to the message above.")

    async def test_on_moderation_action_dm_forbidden_handled(self):
        self.member.send.side_effect = discord.Forbidden(MagicMock(), "Cannot DM")
        case_id = await self.cog.on_moderation_action(
            InfractionsEnum.Warn,
            self.member,
            self.guild,
            "Warn reason",
            self.moderator,
        )
        self.assertIsInstance(case_id, int)

    async def test_on_moderation_action_string_and_enum_delegation(self):
        case_id_ban = await self.cog.on_moderation_ban(
            self.member,
            self.guild,
            "Ban delegation",
            self.moderator,
        )
        self.assertIsInstance(case_id_ban, int)

        case_id_kick = await self.cog.on_moderation_kick(
            self.member,
            self.guild,
            "Kick delegation",
            self.moderator,
        )
        self.assertIsInstance(case_id_kick, int)

        case_id_timeout = await self.cog.on_moderation_timeout(
            self.member,
            self.guild,
            "Timeout delegation",
            self.moderator,
            duration=timedelta(seconds=30),
        )
        self.assertIsInstance(case_id_timeout, int)

        case_id_warn = await self.cog.on_moderation_warn(
            self.member,
            self.guild,
            "Warn delegation",
            self.moderator,
        )
        self.assertIsInstance(case_id_warn, int)


class TestModerationSenders(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_client = MagicMock()
        self.mock_client.boot_time = datetime.now()
        self.mock_client.user = MagicMock(spec=discord.ClientUser)
        self.mock_client.user.id = 999000
        self.mock_client.dispatch = MagicMock()

        self.guild = create_mock_guild(bot_top_role_pos=10)
        self.moderator = create_mock_member(user_id=1, name="Moderator", top_role_pos=9)
        self.target = create_mock_member(user_id=2, name="Target", top_role_pos=5)
        self.ctx = create_mock_context(self.guild, self.moderator)

    async def test_ban_sender_confirm(self):
        cog = Ban(self.mock_client)
        with patch("extensions.moderation.ban.ButtonConfirm") as mock_confirm_cls:
            mock_view = AsyncMock()
            mock_view.value = True
            mock_confirm_cls.return_value = mock_view

            await cog.ban.callback(cog, self.ctx, self.target, "Rule break")

            self.mock_client.dispatch.assert_called_once_with(
                "moderation_action",
                InfractionsEnum.Ban,
                self.target,
                self.guild,
                "Rule break",
                self.moderator,
                ctx=self.ctx,
            )

    async def test_ban_sender_cancelled(self):
        cog = Ban(self.mock_client)
        with patch("extensions.moderation.ban.ButtonConfirm") as mock_confirm_cls:
            mock_view = AsyncMock()
            mock_view.value = False
            mock_confirm_cls.return_value = mock_view

            await cog.ban.callback(cog, self.ctx, self.target, "Rule break")
            self.mock_client.dispatch.assert_not_called()

    async def test_ban_sender_role_hierarchy(self):
        cog = Ban(self.mock_client)
        high_role_target = create_mock_member(user_id=3, name="HigherRole", top_role_pos=15)
        await cog.ban.callback(cog, self.ctx, high_role_target, "Rule break")
        self.mock_client.dispatch.assert_not_called()
        self.ctx.response.send_message.assert_awaited_once()

    async def test_kick_sender_confirm(self):
        cog = Kick(self.mock_client)
        with patch("extensions.moderation.kick.ButtonConfirm") as mock_confirm_cls:
            mock_view = AsyncMock()
            mock_view.value = True
            mock_confirm_cls.return_value = mock_view

            await cog.kick.callback(cog, self.ctx, self.target, "Disruptive")

            self.mock_client.dispatch.assert_called_once_with(
                "moderation_action",
                InfractionsEnum.Kick,
                self.target,
                self.guild,
                "Disruptive",
                self.moderator,
                ctx=self.ctx,
            )

    async def test_timeout_sender_and_duration_parser(self):
        cog = Timeout(self.mock_client)
        # Test duration parsing
        logger_mock = MagicMock()
        self.assertEqual(_parse_duration("10s", logger_mock), timedelta(seconds=10))
        self.assertEqual(_parse_duration("5m", logger_mock), timedelta(minutes=5))
        self.assertEqual(_parse_duration("2h", logger_mock), timedelta(hours=2))
        self.assertEqual(_parse_duration("3d", logger_mock), timedelta(days=3))
        self.assertEqual(_parse_duration("2w", logger_mock), timedelta(weeks=2))
        self.assertEqual(_parse_duration("4w", logger_mock), timedelta(days=27, hours=23, minutes=59))
        self.assertEqual(_parse_duration("invalid", logger_mock), timedelta(seconds=1))

        # Test command invocation
        await cog.timeout.callback(cog, self.ctx, self.target, "5m", "Cooldown")
        self.mock_client.dispatch.assert_called_once_with(
            "moderation_action",
            InfractionsEnum.Timeout,
            self.target,
            self.guild,
            "Cooldown",
            self.moderator,
            ctx=self.ctx,
            duration=timedelta(minutes=5),
        )

    async def test_timeout_sender_bot_check(self):
        cog = Timeout(self.mock_client)
        bot_target = create_mock_member(user_id=4, name="BotTarget")
        bot_target.bot = True
        await cog.timeout.callback(cog, self.ctx, bot_target, "5m", "Cooldown")
        self.mock_client.dispatch.assert_not_called()
        self.ctx.response.send_message.assert_awaited_once()

    async def test_warn_sender_confirm(self):
        cog = Warn(self.mock_client)
        with patch("extensions.moderation.warn.ButtonConfirm") as mock_confirm_cls:
            mock_view = AsyncMock()
            mock_view.value = True
            mock_confirm_cls.return_value = mock_view

            await cog.warn.callback(cog, self.ctx, self.target, "Off-topic")

            self.mock_client.dispatch.assert_called_once_with(
                "moderation_action",
                InfractionsEnum.Warn,
                self.target,
                self.guild,
                "Off-topic",
                self.moderator,
                ctx=self.ctx,
            )

    async def test_safebrowsing_sender(self):
        cog = SafebrowsingCog(self.mock_client)
        msg = MagicMock(spec=discord.Message)
        msg.author = self.target
        msg.guild = self.guild
        msg.content = "Check out https://evil-phishing.com/login"
        msg.delete = AsyncMock()

        with patch.object(cog, "_filter_urls", new=AsyncMock(return_value=["evil-phishing.com/login"])):
            await cog.message_event(msg)

            msg.delete.assert_awaited_once_with(reason="Detected as bad url")
            self.mock_client.dispatch.assert_called_once()
            call_args = self.mock_client.dispatch.call_args
            self.assertEqual(call_args[0][0], "moderation_action")
            self.assertEqual(call_args[0][1], InfractionsEnum.Warn)
            self.assertEqual(call_args[0][2], self.target)
            self.assertEqual(call_args[0][3], self.guild)
            self.assertEqual(call_args[0][4], "Bad URL sent")
            self.assertEqual(call_args[0][5], self.mock_client.user)
            self.assertEqual(call_args[1]["log_reason"], "Sending a malicious link")
            self.assertEqual(call_args[1]["embed_title"], "Message delete")
            self.assertEqual(call_args[1]["dm_info_text"], "You were warned due to the message above.")
            self.assertEqual(len(call_args[1]["extra_embeds"]), 1)


if __name__ == "__main__":
    unittest.main()
