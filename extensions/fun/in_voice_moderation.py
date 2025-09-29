from random import choice

import discord
from discord import ui
from discord.ext import commands

import utils
from utils import Bot, CustomLogger, Settings, SettingsEnum

class Mute(discord.ui.Button): 
    def __init__(self, user: discord.Member, ctx: discord.ApplicationContext):
        super().__init__(label="Mute")
        self.channel_ctx = ctx
        self.user = user
        self.muted = self.user.voice.mute
        if self.muted:
            self.emoji = ":speak_no_evil:"
            self.style = discord.ButtonStyle.red
        else:
            self.emoji = ":monkey_face:"
            self.style = discord.ButtonStyle.green
        

    async def callback(self, interaction):
        if self.user.voice.channel == self.channel_ctx:
            if self.muted:
                await self.unmute()
                self.emoji = ":monkey_face:"
                self.style = discord.ButtonStyle.green
            else:
                await self.mute()
                self.emoji = ":speak_no_evil:"
                self.style = discord.ButtonStyle.red
            
        await interaction.response.edit_message(view=self.view)

    async def mute(self):

        await self.user.edit(mute=True)
        self.muted = True

    async def unmute(self):
        await self.user.edit(mute=False)
        self.muted = False

class Deaf(discord.ui.Button):
    def __init__(self, user:discord.Member ,ctx: discord.ApplicationContext):
        super().__init__(label="Deaf")
        self.channel_ctx = ctx
        self.user = user
        self.deafed = self.user.voice.deaf
        if self.deafed:
            self.emoji = ":hear_no_evil:"
            self.style = discord.ButtonStyle.red
        else:
            self.emoji = ":monkey_face:"
            self.style = discord.ButtonStyle.green

    async def callback(self, interaction):
        if self.user.voice.channel == self.channel_ctx:
            if self.deafed:
                await self.undeaf()
                self.emoji = ":monkey_face:"
                self.style = discord.ButtonStyle.green
            else:
                await self.deaf()
                self.emoji = ":hear_no_evil:"
                self.style = discord.ButtonStyle.red
        await interaction.response.edit_message(view=self.view)

    async def deaf(self):
        await self.user.edit(deafen=True)
        self.deafed = True

    async def undeaf(self):
        await self.user.edit(deafen=False)
        self.deafed = False


class MuteView(discord.ui.View):
    def __init__(self, channel_ctx: discord.VoiceChannel):
        super().__init__()
        self.channel = channel_ctx
        self.user_in_channel = self.channel.members
        container = discord.ui.Container()
        for user in self.user_in_channel:
            mute = discord.ui.Section(
                discord.ui.TextDisplay(content=user.display_name),
                accessory=Mute(user, ctx = channel_ctx)
            )
            deaf = discord.ui.Section(
                discord.ui.TextDisplay(content=user.display_name),
                accessory=Deaf(user, ctx = channel_ctx)
            )
            container.add_item(item=mute)
            container.add_item(item=deaf)
            container.add_separator()
        self.add_item(container)

class DnDManager(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)
        # {
        #   channel_id: user
        # }
        self.claimed = {}
        self.requested_message = {}

    @commands.slash_command(name="claim", description="Claim this channel to moderate it")
    async def claim(self, ctx: discord.ApplicationContext):
        if isinstance(ctx.channel, discord.VoiceChannel):
            try:
                guild_claim = self.claimed[ctx.channel_id]
                await ctx.response.send_message(f"This channel is already claimed by {guild_claim.display_name}",ephemeral=True,delete_after=5.0)
            except KeyError:
                self.claimed[ctx.channel_id] = ctx.user
                await ctx.response.send_message("You claimed this channel",ephemeral=True,delete_after=5.0)
        else:
            await ctx.response.send_message("This is not a voice channel",ephemeral=True,delete_after=5.0)

    @commands.slash_command(name="unclaim", description="Unclaims the channel")
    async def unclaim(self, ctx: discord.ApplicationContext):
        if isinstance(ctx.channel, discord.VoiceChannel):
            try:
                guild_claim = self.claimed[ctx.channel_id]
                if guild_claim == ctx.user or ctx.user.guild_permissions.administrator:
                    del self.claimed[ctx.channel_id]
                    try:
                        await self.requested_message[ctx.user.id].delete_original_message()
                        del self.requested_message[ctx.user.id]
                    except KeyError:
                        pass
                    for member in ctx.channel.members:
                        await member.edit(deafen=False, mute=False)
                    await ctx.response.send_message("You unclaimed this channel",ephemeral=True,delete_after=5.0)
                else:
                    await ctx.response.send_message("Only the owner or an admin can unclaim the channel",ephemeral=True,delete_after=5.0)
            except KeyError:
                await ctx.response.send_message("Channel is unclaimed",ephemeral=True,delete_after=5.0)
        else:
            await ctx.response.send_message("This is not a voice channel",ephemeral=True,delete_after=5.0)


    @commands.slash_command(name="moderate", description="moderate user in this channel")
    async def moderate(self, ctx: discord.ApplicationContext):
        if isinstance(ctx.channel, discord.VoiceChannel):
            try:
                guild_claim = self.claimed[ctx.channel_id]
                if guild_claim == ctx.user or ctx.user.guild_permissions.administrator:
                    message = await ctx.respond(view=MuteView(ctx.channel), ephemeral=True)
                    self.requested_message[ctx.user.id] = message
                else:
                    await ctx.response.send_message("You are not the owner of this channel",ephemeral=True,delete_after=5.0)
            except KeyError:
                await ctx.response.send_message("Channel is unclaimed. \nClaim this channel by using the /claim command",ephemeral=True,delete_after=5.0)
        else:
            await ctx.response.send_message("This is not a voice channel",ephemeral=True,delete_after=5.0)
    
    @commands.Cog.listener("on_guild_channel_delete")
    async def channel_delete(self, ctx: discord.abc.GuildChannel):
        try:
            self.claimed[ctx.id]
            del self.claimed[ctx.id]
            if isinstance(ctx, discord.VoiceChannel):
                for member in ctx.members:
                    await member.edit(deafen=False, mute=False)
        except KeyError:
            pass
    
    @commands.Cog.listener("on_voice_state_update")
    async def channel_left(self, member, before, after):
        if before.channel is not None and after.channel is not None:
            if before.channel != after.channel:
                if before.channel.id in self.claimed.keys():
                    await member.edit(deafen=False, mute=False)

def setup(client: Bot):
    client.add_cog(DnDManager(client))
