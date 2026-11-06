from datetime import datetime
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from extensions.moderation.moveall import MoveAll, setup
from utils import Bot


def create_mock_perms(move_members: bool = True, connect: bool = True) -> MagicMock:
    perms = MagicMock(spec=discord.Permissions)
    perms.move_members = move_members
    perms.connect = connect
    return perms


class TestMoveAll(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = MagicMock(spec=Bot)
        self.client.boot_time = datetime.now()
        self.client.db = AsyncMock()
        self.client.db.get_setting = AsyncMock(return_value=None)
        self.cog = MoveAll(self.client)
        self.cog.moveall.cog = self.cog

        self.ctx = AsyncMock(spec=discord.ApplicationContext)
        self.ctx.guild = MagicMock(spec=discord.Guild)
        self.ctx.guild.id = 123456
        self.ctx.guild.me = MagicMock(spec=discord.Member)

        self.ctx.author = MagicMock(spec=discord.Member)
        self.ctx.author.guild_permissions = discord.Permissions(administrator=False)
        self.ctx.author.roles = []
        self.ctx.author.__str__ = MagicMock(return_value="ModUser#1234")

        self.ctx.response = MagicMock()
        self.ctx.response.is_done = MagicMock(return_value=False)
        self.ctx.response.send_message = AsyncMock()
        self.ctx.response.defer = AsyncMock()
        self.ctx.followup = MagicMock()
        self.ctx.followup.send = AsyncMock()

        self.source = MagicMock(spec=discord.VoiceChannel)
        self.source.id = 101
        self.source.mention = "<#101>"
        self.source.members = []

        self.destination = MagicMock(spec=discord.VoiceChannel)
        self.destination.id = 202
        self.destination.mention = "<#202>"
        self.destination.user_limit = 5
        self.destination.members = []

        # Default permissions: author and bot have required perms
        self.author_source_perms = create_mock_perms(move_members=True, connect=True)
        self.author_dest_perms = create_mock_perms(move_members=True, connect=True)
        self.bot_source_perms = create_mock_perms(move_members=True, connect=True)
        self.bot_dest_perms = create_mock_perms(move_members=True, connect=True)

        def source_permissions_for(member):
            if member == self.ctx.guild.me:
                return self.bot_source_perms
            return self.author_source_perms

        def dest_permissions_for(member):
            if member == self.ctx.guild.me:
                return self.bot_dest_perms
            return self.author_dest_perms

        self.source.permissions_for.side_effect = source_permissions_for
        self.destination.permissions_for.side_effect = dest_permissions_for

    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_successful_mass_move_ignores_user_limit(self, mock_sleep):
        m1 = AsyncMock(spec=discord.Member)
        m2 = AsyncMock(spec=discord.Member)
        m3 = AsyncMock(spec=discord.Member)
        self.source.members = [m1, m2, m3]
        # Target channel user limit is 1, but we have 3 members to move (should ignore limit)
        self.destination.user_limit = 1

        await self.cog.moveall(self.ctx, self.source, self.destination)

        self.ctx.response.defer.assert_awaited_once_with(ephemeral=True)
        m1.move_to.assert_awaited_once_with(self.destination, reason="Mass move by ModUser#1234")
        m2.move_to.assert_awaited_once_with(self.destination, reason="Mass move by ModUser#1234")
        m3.move_to.assert_awaited_once_with(self.destination, reason="Mass move by ModUser#1234")
        self.assertEqual(mock_sleep.await_count, 2)
        mock_sleep.assert_awaited_with(0.15)

        self.ctx.followup.send.assert_awaited_once_with(
            "Successfully moved 3 members from <#101> to <#202>.",
            ephemeral=True,
        )

    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_successful_single_member_move_no_sleep(self, mock_sleep):
        m1 = AsyncMock(spec=discord.Member)
        self.source.members = [m1]

        await self.cog.moveall(self.ctx, self.source, self.destination)

        self.ctx.response.defer.assert_awaited_once_with(ephemeral=True)
        m1.move_to.assert_awaited_once_with(self.destination, reason="Mass move by ModUser#1234")
        mock_sleep.assert_not_awaited()

        self.ctx.followup.send.assert_awaited_once_with(
            "Successfully moved 1 member from <#101> to <#202>.",
            ephemeral=True,
        )

    async def test_rejects_identical_source_and_destination(self):
        self.destination.id = self.source.id

        await self.cog.moveall(self.ctx, self.source, self.destination)

        self.ctx.response.send_message.assert_awaited_once_with(
            "Source and destination channels must not be identical.",
            ephemeral=True,
        )
        self.ctx.response.defer.assert_not_awaited()

    async def test_rejects_empty_source_channel(self):
        self.source.members = []

        await self.cog.moveall(self.ctx, self.source, self.destination)

        self.ctx.response.send_message.assert_awaited_once_with(
            "There are currently no members in the source channel.",
            ephemeral=True,
        )
        self.ctx.response.defer.assert_not_awaited()

    async def test_rejects_caller_lacking_move_members_in_source(self):
        self.author_source_perms.move_members = False
        self.source.members = [AsyncMock(spec=discord.Member)]

        await self.cog.moveall(self.ctx, self.source, self.destination)

        self.ctx.response.send_message.assert_awaited_once_with(
            "You do not have permission to move members between these channels.",
            ephemeral=True,
        )
        self.ctx.response.defer.assert_not_awaited()

    async def test_rejects_caller_lacking_move_members_in_destination(self):
        self.author_dest_perms.move_members = False
        self.source.members = [AsyncMock(spec=discord.Member)]

        await self.cog.moveall(self.ctx, self.source, self.destination)

        self.ctx.response.send_message.assert_awaited_once_with(
            "You do not have permission to move members between these channels.",
            ephemeral=True,
        )
        self.ctx.response.defer.assert_not_awaited()

    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_allows_guild_administrator_even_without_channel_move_members(self, _mock_sleep):
        self.author_source_perms.move_members = False
        self.author_dest_perms.move_members = False
        self.ctx.author.guild_permissions = discord.Permissions(administrator=True)

        m1 = AsyncMock(spec=discord.Member)
        self.source.members = [m1]

        await self.cog.moveall(self.ctx, self.source, self.destination)

        self.ctx.response.defer.assert_awaited_once_with(ephemeral=True)
        m1.move_to.assert_awaited_once()

    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_allows_team_member_even_without_channel_move_members(self, _mock_sleep):
        self.author_source_perms.move_members = False
        self.author_dest_perms.move_members = False
        team_role_id = 9999
        self.client.db.get_setting.return_value = SimpleNamespace(value=team_role_id)
        self.ctx.author.roles = [SimpleNamespace(id=team_role_id)]

        m1 = AsyncMock(spec=discord.Member)
        self.source.members = [m1]

        await self.cog.moveall(self.ctx, self.source, self.destination)

        self.ctx.response.defer.assert_awaited_once_with(ephemeral=True)
        m1.move_to.assert_awaited_once()

    async def test_rejects_bot_lacking_move_members_in_source(self):
        self.bot_source_perms.move_members = False
        self.source.members = [AsyncMock(spec=discord.Member)]

        await self.cog.moveall(self.ctx, self.source, self.destination)

        self.ctx.response.send_message.assert_awaited_once_with(
            "I lack Move Members or Connect permissions for the channels.",
            ephemeral=True,
        )
        self.ctx.response.defer.assert_not_awaited()

    async def test_rejects_bot_lacking_move_members_in_destination(self):
        self.bot_dest_perms.move_members = False
        self.source.members = [AsyncMock(spec=discord.Member)]

        await self.cog.moveall(self.ctx, self.source, self.destination)

        self.ctx.response.send_message.assert_awaited_once_with(
            "I lack Move Members or Connect permissions for the channels.",
            ephemeral=True,
        )
        self.ctx.response.defer.assert_not_awaited()

    async def test_rejects_bot_lacking_connect_in_destination(self):
        self.bot_dest_perms.connect = False
        self.source.members = [AsyncMock(spec=discord.Member)]

        await self.cog.moveall(self.ctx, self.source, self.destination)

        self.ctx.response.send_message.assert_awaited_once_with(
            "I lack Move Members or Connect permissions for the channels.",
            ephemeral=True,
        )
        self.ctx.response.defer.assert_not_awaited()

    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_continues_moving_when_member_raises_httpexception_or_forbidden(self, _mock_sleep):
        m1 = AsyncMock(spec=discord.Member)
        m2 = AsyncMock(spec=discord.Member)
        m3 = AsyncMock(spec=discord.Member)
        m4 = AsyncMock(spec=discord.Member)

        # m2 raises HTTPException (e.g. left voice)
        m2.move_to.side_effect = discord.HTTPException(MagicMock(status=400), "User left voice")
        # m3 raises Forbidden
        m3.move_to.side_effect = discord.Forbidden(MagicMock(status=403), "Missing Permissions")

        self.source.members = [m1, m2, m3, m4]

        await self.cog.moveall(self.ctx, self.source, self.destination)

        self.ctx.response.defer.assert_awaited_once_with(ephemeral=True)
        m1.move_to.assert_awaited_once()
        m2.move_to.assert_awaited_once()
        m3.move_to.assert_awaited_once()
        m4.move_to.assert_awaited_once()

        self.ctx.followup.send.assert_awaited_once_with(
            "Successfully moved 2 members from <#101> to <#202>.",
            ephemeral=True,
        )

    def test_setup_registers_cog(self):
        mock_bot = MagicMock(spec=Bot)
        mock_bot.boot_time = datetime.now()
        setup(mock_bot)
        mock_bot.add_cog.assert_called_once()
        added_cog = mock_bot.add_cog.call_args[0][0]
        self.assertIsInstance(added_cog, MoveAll)
