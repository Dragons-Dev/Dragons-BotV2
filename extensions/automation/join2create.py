import json
from random import choice

import discord
from discord import ui
from discord.ext import commands

import utils
from utils import Bot, CustomLogger, Settings, SettingsEnum



class Join2Create(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)
        with open("assets/suffix.json") as f:
            self.status = json.load(f)
            self.suffixes = [*self.status]

    @commands.Cog.listener("on_voice_state_update")
    async def on_join2create(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """
        Checks if a person joins a dedicated voice channel. If so creates a new voice channel and moves the person to it
        Creates a new database entry for the new voice channel and deletes it if everyone left it.

        Args:
            member (discord.Member): member who updated his voice state
            before (discord.VoiceState): members voice state before
            after (discord.VoiceState): members voice state after
        """
        if before.channel == after.channel:
            return
        if after.channel is not None:
            join2create_setting = await self.client.db.get_setting(
                setting=SettingsEnum.Join2CreateChannel, guild=member.guild
            )
            if join2create_setting is None:
                return
            if type(join2create_setting) is not Settings:
                return
            if after.channel.id == join2create_setting.value:
                verified_role = await self.client.db.get_setting(setting=SettingsEnum.VerifiedRole, guild=member.guild)
                if verified_role is None:
                    role = member.guild.default_role
                elif type(verified_role) is not Settings:
                    role = member.guild.default_role  # I don't like you mypy this overhead is only for you!
                else:
                    role = member.guild.get_role(verified_role.value)
                perms = {
                    role: discord.PermissionOverwrite(
                        stream=True,
                        connect=True,
                        speak=True,
                        use_voice_activation=True,
                        read_message_history=True,
                        read_messages=True,
                        send_messages=True,
                    ),
                    member: discord.PermissionOverwrite(
                        move_members=True, view_channel=True, use_external_apps=True, connect=True, send_messages=True
                    ),
                    self.client.user: discord.PermissionOverwrite(
                        move_members=True, manage_channels=True, view_channel=True
                    ),
                }
                if member.guild.premium_subscriber_role:
                    perms[member.guild.premium_subscriber_role] = discord.PermissionOverwrite(move_members=True)
                if member.guild.default_role != role:
                    perms[member.guild.default_role] = discord.PermissionOverwrite(view_channel=False)
                else:
                    perms[member.guild.default_role] = discord.PermissionOverwrite(view_channel=True)
                channel_name = choice(self.suffixes)
                member_name = member.display_name
                if member_name[-1].lower() != "s":
                    if self.status[channel_name]["s_flag"]:
                        member_name += "s"

                try:
                    channel = await after.channel.category.create_voice_channel(
                        name=f"{member_name}{channel_name}",
                        user_limit=25,
                        reason="Join2Create",
                        overwrites=perms,
                    )
                except (discord.Forbidden, discord.HTTPException, discord.InvalidArgument) as e:
                    self.logger.error(e)
                    return

                if self.status[channel_name]:
                    status = choice(self.status[channel_name]["status"])
                    await channel.set_status(status=status, reason="Join2Create")

                check = await self.client.db.create_temp_voice(channel, member)
                if not check:
                    await channel.delete(reason="Join2Create-Failed")
                    self.logger.error("Database entry for temp voice channel could not be created")
                    return
                self.logger.debug(f"{member.name} created {channel.name} in {member.guild}")
                try:
                    await member.move_to(channel)
                except (discord.Forbidden, discord.HTTPException) as e:
                    self.logger.error(f"Couldn't move member | {e}")
                    return
                # Here was the voice board created before
                # TODO: Reimplement VoiceBoard

        if before.channel is not None:
            if await self.client.db.get_temp_voice(before.channel):
                if len([m for m in before.channel.members if not m.bot]) == 0:
                    await self.client.db.delete_temp_voice(before.channel)
                    self.logger.debug(f"{before.channel.name} was deleted on {member.guild}")
                    await before.channel.delete(reason="Join2Delete")


    @commands.Cog.listener("on_ready", once=True)
    async def on_ready(self):
        return
        self.client.add_view(VoiceBoard())
        self.logger.info("Added persistent view for VoiceBoard")


def setup(client: Bot):
    client.add_cog(Join2Create(client))
