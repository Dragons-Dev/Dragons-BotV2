from unittest.mock import AsyncMock, MagicMock, patch
import unittest

import discord

from extensions.automation.join2create import (
    BanRole,
    BanUser,
    Join2Create,
    build_join2create_overwrites,
    reset_permission,
    transfer_ownership,
)
from extensions.automation.models import Join2Create as Join2CreateModel
from utils.enums import SettingsEnum
from utils.orm_database.models import Settings


class TestJoin2Create(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.logger_patch = patch("extensions.automation.join2create.CustomLogger")
        self.mock_logger = self.logger_patch.start()
        self.addCleanup(self.logger_patch.stop)

        self.bot = MagicMock()
        self.bot.boot_time = MagicMock()
        self.bot.user = MagicMock()
        self.bot.user.color = discord.Color.blue()
        self.bot.db = MagicMock()
        self.bot.get_or_fetch = AsyncMock()

        self.guild = MagicMock(spec=discord.Guild)
        self.team_role = MagicMock(spec=discord.Role)
        self.team_role.id = 1001
        self.team_role.mention = "<@&1001>"

        self.other_role = MagicMock(spec=discord.Role)
        self.other_role.id = 1002
        self.other_role.mention = "<@&1002>"

        self.owner = MagicMock(spec=discord.Member)
        self.owner.id = 2001
        self.owner.mention = "<@2001>"
        self.owner.roles = []

        self.team_member = MagicMock(spec=discord.Member)
        self.team_member.id = 2002
        self.team_member.mention = "<@2002>"
        self.team_member.roles = [self.team_role]

        self.regular_user = MagicMock(spec=discord.Member)
        self.regular_user.id = 2003
        self.regular_user.mention = "<@2003>"
        self.regular_user.roles = []

        self.guild.get_role.side_effect = lambda role_id: self.team_role if role_id == self.team_role.id else None
        self.guild.get_member.side_effect = lambda member_id: {
            self.owner.id: self.owner,
            self.team_member.id: self.team_member,
            self.regular_user.id: self.regular_user,
        }.get(member_id)

    async def test_build_overwrites_with_team_role_and_owner(self):
        # Base overwrite on derived channel for team_role has send_messages=True, move_members=False
        existing_team_ow = discord.PermissionOverwrite(send_messages=True, move_members=False)
        derived_overwrites = {self.team_role: existing_team_ow}

        team_setting = Settings(guild=self.guild.id, setting=SettingsEnum.TeamRole, value=self.team_role.id)
        self.bot.db.get_setting = AsyncMock(return_value=team_setting)

        overwrites = await build_join2create_overwrites(
            derived_overwrites=derived_overwrites,
            guild=self.guild,
            owner=self.owner,
            bot=self.bot,
        )

        # TeamRole overwrite should preserve send_messages=True, and set view_channel, connect, move_members to True
        team_ow = overwrites[self.team_role]
        self.assertTrue(team_ow.send_messages)
        self.assertTrue(team_ow.view_channel)
        self.assertTrue(team_ow.connect)
        self.assertTrue(team_ow.move_members)

        # Owner overwrite should have view_channel, connect, move_members set to True
        owner_ow = overwrites[self.owner]
        self.assertTrue(owner_ow.view_channel)
        self.assertTrue(owner_ow.connect)
        self.assertTrue(owner_ow.move_members)

    async def test_build_overwrites_without_team_role_setting(self):
        self.bot.db.get_setting = AsyncMock(return_value=None)
        derived_overwrites = {}

        overwrites = await build_join2create_overwrites(
            derived_overwrites=derived_overwrites,
            guild=self.guild,
            owner=self.owner,
            bot=self.bot,
        )

        self.assertNotIn(self.team_role, overwrites)
        self.assertIn(self.owner, overwrites)
        self.assertTrue(overwrites[self.owner].move_members)

    async def test_build_overwrites_team_role_not_found_in_guild(self):
        team_setting = Settings(guild=self.guild.id, setting=SettingsEnum.TeamRole, value=9999)
        self.bot.db.get_setting = AsyncMock(return_value=team_setting)
        self.guild.get_role.return_value = None
        self.guild.get_or_fetch = AsyncMock(return_value=None)

        overwrites = await build_join2create_overwrites(
            derived_overwrites={},
            guild=self.guild,
            owner=self.owner,
            bot=self.bot,
        )

        self.assertNotIn(self.team_role, overwrites)
        self.assertIn(self.owner, overwrites)

    async def test_reset_permission_applies_team_role_and_owner_overwrites(self):
        interaction = MagicMock(spec=discord.Interaction)
        interaction.client = self.bot
        interaction.user = self.owner
        interaction.respond = AsyncMock()

        channel = MagicMock(spec=discord.VoiceChannel)
        channel.guild = self.guild
        channel.edit = AsyncMock()

        derived_channel = MagicMock(spec=discord.VoiceChannel)
        derived_channel.overwrites = {self.team_role: discord.PermissionOverwrite(speak=True)}
        derived_channel.mention = "<#100>"

        self.bot.get_or_fetch = AsyncMock(return_value=derived_channel)
        team_setting = Settings(guild=self.guild.id, setting=SettingsEnum.TeamRole, value=self.team_role.id)
        self.bot.db.get_setting = AsyncMock(return_value=team_setting)

        current_j2c = Join2CreateModel(channel=channel.id, owner_id=self.owner.id, derived_channel=derived_channel.id)

        await reset_permission(interaction, channel, current_j2c)

        channel.edit.assert_awaited_once()
        saved_overwrites = channel.edit.call_args.kwargs["overwrites"]
        self.assertTrue(saved_overwrites[self.team_role].move_members)
        self.assertTrue(saved_overwrites[self.team_role].speak)
        self.assertTrue(saved_overwrites[self.owner].move_members)
        interaction.respond.assert_awaited_once()

    async def test_reset_permission_derived_channel_not_found(self):
        interaction = MagicMock(spec=discord.Interaction)
        interaction.client = self.bot
        interaction.respond = AsyncMock()
        channel = MagicMock(spec=discord.VoiceChannel)

        self.bot.get_or_fetch = AsyncMock(return_value=None)
        current_j2c = Join2CreateModel(channel=channel.id, owner_id=self.owner.id, derived_channel=999)

        await reset_permission(interaction, channel, current_j2c)

        channel.edit.assert_not_called()
        interaction.respond.assert_awaited_once()
        self.assertIn("Couldn't find original", interaction.respond.call_args.args[0])

    async def test_transfer_ownership_updates_new_owner_permissions(self):
        interaction = MagicMock(spec=discord.Interaction)
        interaction.client = self.bot
        interaction.user = self.regular_user  # claiming ownership
        interaction.respond = AsyncMock()
        interaction.message = MagicMock()
        interaction.message.edit = AsyncMock()

        channel = MagicMock(spec=discord.VoiceChannel)
        channel.members = [self.regular_user]  # old owner is no longer in channel
        channel.overwrites = {}
        channel.set_permissions = AsyncMock()

        temp_voice = Join2CreateModel(channel=channel.id, owner_id=self.owner.id, derived_channel=100)

        with patch("extensions.automation.join2create.Join2CreateRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.update = AsyncMock()
            mock_repo_class.return_value = mock_repo

            await transfer_ownership(interaction, channel, temp_voice)

            mock_repo.update.assert_awaited_once_with(channel, self.regular_user)
            channel.set_permissions.assert_awaited_once()
            called_user, called_kwargs = channel.set_permissions.call_args[0][0], channel.set_permissions.call_args[1]
            self.assertEqual(called_user, self.regular_user)
            self.assertTrue(called_kwargs["overwrite"].move_members)
            self.assertTrue(called_kwargs["overwrite"].view_channel)
            self.assertTrue(called_kwargs["overwrite"].connect)

    async def test_ban_role_filters_team_role(self):
        modal = BanRole()
        select_mock = MagicMock()
        select_mock.values = [self.team_role, self.other_role]
        modal.children[0].item = select_mock

        interaction = MagicMock(spec=discord.Interaction)
        interaction.client = self.bot
        interaction.guild = self.guild
        interaction.respond = AsyncMock()

        channel = MagicMock(spec=discord.VoiceChannel)
        channel.overwrites = {}
        channel.edit = AsyncMock()
        interaction.channel = channel

        team_setting = Settings(guild=self.guild.id, setting=SettingsEnum.TeamRole, value=self.team_role.id)
        self.bot.db.get_setting = AsyncMock(return_value=team_setting)

        with patch("extensions.automation.join2create.create_overwrite_from_select") as mock_create_ow:
            mock_create_ow.return_value = {self.other_role: discord.PermissionOverwrite()}
            await modal.callback(interaction)

            mock_create_ow.assert_awaited_once()
            passed_roles = mock_create_ow.call_args.kwargs["overwrite_items"]
            # Team role should be filtered out
            self.assertEqual(passed_roles, [self.other_role])
            channel.edit.assert_awaited_once()
            interaction.respond.assert_awaited_once()
            self.assertIn(self.other_role.mention, interaction.respond.call_args.args[0])

    async def test_ban_role_only_team_role_selected(self):
        modal = BanRole()
        select_mock = MagicMock()
        select_mock.values = [self.team_role]
        modal.children[0].item = select_mock

        interaction = MagicMock(spec=discord.Interaction)
        interaction.client = self.bot
        interaction.guild = self.guild
        interaction.respond = AsyncMock()
        channel = MagicMock(spec=discord.VoiceChannel)
        interaction.channel = channel

        team_setting = Settings(guild=self.guild.id, setting=SettingsEnum.TeamRole, value=self.team_role.id)
        self.bot.db.get_setting = AsyncMock(return_value=team_setting)

        await modal.callback(interaction)

        channel.edit.assert_not_called()
        interaction.respond.assert_awaited_once_with("The team role cannot be banned.", ephemeral=True)

    async def test_ban_user_filters_team_member_self_and_bot(self):
        modal = BanUser()
        bot_user = MagicMock(spec=discord.Member)
        bot_user.id = 9999
        self.bot.user = bot_user

        select_mock = MagicMock()
        select_mock.values = [self.owner, bot_user, self.team_member, self.regular_user]
        modal.children[0].item = select_mock

        interaction = MagicMock(spec=discord.Interaction)
        interaction.client = self.bot
        interaction.user = self.owner
        interaction.guild = self.guild
        interaction.respond = AsyncMock()

        channel = MagicMock(spec=discord.VoiceChannel)
        channel.members = [self.regular_user]
        channel.edit = AsyncMock()
        interaction.channel = channel

        team_setting = Settings(guild=self.guild.id, setting=SettingsEnum.TeamRole, value=self.team_role.id)
        self.bot.db.get_setting = AsyncMock(return_value=team_setting)

        with patch("extensions.automation.join2create.create_overwrite_from_select") as mock_create_ow:
            mock_create_ow.return_value = {self.regular_user: discord.PermissionOverwrite()}
            self.regular_user.move_to = AsyncMock()

            await modal.callback(interaction)

            mock_create_ow.assert_awaited_once()
            passed_users = mock_create_ow.call_args.kwargs["overwrite_items"]
            # Owner (self), bot, and team_member should be filtered out
            self.assertEqual(passed_users, [self.regular_user])
            channel.edit.assert_awaited_once()
            self.regular_user.move_to.assert_awaited_once()
            interaction.respond.assert_awaited_once()

    async def test_ban_user_only_team_members_selected(self):
        modal = BanUser()
        bot_user = MagicMock(spec=discord.Member)
        bot_user.id = 9999
        self.bot.user = bot_user

        select_mock = MagicMock()
        select_mock.values = [self.owner, bot_user, self.team_member]
        modal.children[0].item = select_mock

        interaction = MagicMock(spec=discord.Interaction)
        interaction.client = self.bot
        interaction.user = self.owner
        interaction.guild = self.guild
        interaction.respond = AsyncMock()
        channel = MagicMock(spec=discord.VoiceChannel)
        interaction.channel = channel

        team_setting = Settings(guild=self.guild.id, setting=SettingsEnum.TeamRole, value=self.team_role.id)
        self.bot.db.get_setting = AsyncMock(return_value=team_setting)

        await modal.callback(interaction)

        channel.edit.assert_not_called()
        interaction.respond.assert_awaited_once_with(
            "You cannot ban yourself, the bot, or team members.", ephemeral=True
        )

    async def test_on_join2create_creates_channel_with_team_role_overwrites(self):
        client = MagicMock()
        client.boot_time = MagicMock()
        client.user = MagicMock()
        client.user.color = discord.Color.blue()
        cog = Join2Create(client)
        cog.join2create_repo = MagicMock()
        cog.join2create_repo.create = AsyncMock(return_value=True)

        j2c_channel_id = 5001
        j2c_setting = Settings(guild=self.guild.id, setting=SettingsEnum.Join2CreateChannel, value=j2c_channel_id)
        team_setting = Settings(guild=self.guild.id, setting=SettingsEnum.TeamRole, value=self.team_role.id)

        async def mock_get_setting(setting, guild):
            if setting == SettingsEnum.Join2CreateChannel:
                return j2c_setting
            elif setting == SettingsEnum.TeamRole:
                return team_setting
            return None

        client.db.get_setting = AsyncMock(side_effect=mock_get_setting)

        before = MagicMock(spec=discord.VoiceState)
        before.channel = None

        category = MagicMock(spec=discord.CategoryChannel)
        new_channel = MagicMock(spec=discord.VoiceChannel)
        new_channel.name = "Test Channel"
        new_channel.send = AsyncMock()
        new_channel.set_status = AsyncMock()
        category.create_voice_channel = AsyncMock(return_value=new_channel)

        trigger_channel = MagicMock(spec=discord.VoiceChannel)
        trigger_channel.id = j2c_channel_id
        trigger_channel.category = category
        trigger_channel.overwrites = {}

        after = MagicMock(spec=discord.VoiceState)
        after.channel = trigger_channel

        member = MagicMock(spec=discord.Member)
        member.guild = self.guild
        member.display_name = "Dragon"
        member.name = "dragon"
        member.move_to = AsyncMock()

        await cog.on_join2create(member, before, after)

        category.create_voice_channel.assert_awaited_once()
        created_overwrites = category.create_voice_channel.call_args.kwargs["overwrites"]

        self.assertIn(self.team_role, created_overwrites)
        self.assertTrue(created_overwrites[self.team_role].move_members)
        self.assertIn(member, created_overwrites)
        self.assertTrue(created_overwrites[member].move_members)
