import discord
from discord.ext import commands
import pycord.multicog as pycog

from utils import Bot, CustomLogger


class Mute(discord.ui.Button):
    def __init__(self, user: discord.Member, ctx: discord.ApplicationContext):
        super().__init__(label="Mute")
        self.channel_ctx = ctx
        self.user = user
        if self.user.voice.mute:
            self.emoji = ":speak_no_evil:"
            self.style = discord.ButtonStyle.red
        else:
            self.emoji = ":monkey_face:"
            self.style = discord.ButtonStyle.green

    async def callback(self, interaction):
        if self.user.voice.channel == self.channel_ctx:
            if self.user.voice.mute:
                await self.user.edit(mute=False)
                self.emoji = ":monkey_face:"
                self.style = discord.ButtonStyle.green
            else:
                await self.user.edit(mute=True)
                self.emoji = ":speak_no_evil:"
                self.style = discord.ButtonStyle.red

        await interaction.response.edit_message(view=self.view)


class Deaf(discord.ui.Button):
    def __init__(self, user: discord.Member, ctx: discord.ApplicationContext):
        super().__init__(label="Deaf")
        self.channel_ctx = ctx
        self.user = user
        if self.user.voice.deaf:
            self.emoji = ":hear_no_evil:"
            self.style = discord.ButtonStyle.red
        else:
            self.emoji = ":monkey_face:"
            self.style = discord.ButtonStyle.green

    async def callback(self, interaction):
        if self.user.voice.channel == self.channel_ctx:
            if self.user.voice.deaf:
                await self.user.edit(deafen=False)
                self.emoji = ":monkey_face:"
                self.style = discord.ButtonStyle.green
            else:
                await self.user.edit(deafen=True)
                self.emoji = ":hear_no_evil:"
                self.style = discord.ButtonStyle.red
        await interaction.response.edit_message(view=self.view)


class MuteView(discord.ui.View):
    def __init__(self, channel_ctx: discord.VoiceChannel):
        super().__init__()
        self.channel = channel_ctx
        self.user_in_channel = self.channel.members
        # container = discord.ui.Container()
        # container.add_separator()
        self.row = 0
        for member in self.user_in_channel[:13]:  # 13 * 3 Components = 39, noch sicher
            # Button mit Name (disabled, nur Anzeige)
            name_button = discord.ui.Button(
                label=member.display_name, style=discord.ButtonStyle.gray, disabled=True, row=self.row
            )

            mute_button = Mute(user=member, ctx=self.channel)
            mute_button.row = self.row

            deafen_button = Deaf(user=member, ctx=self.channel)
            deafen_button.row = self.row

            self.add_item(name_button)
            self.add_item(mute_button)
            self.add_item(deafen_button)
            self.row += 1


class InVoiceModeration(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)
        # {
        #   channel_id: user
        # }
        self.claimed = {}
        # {
        #   channel_id: message
        # }
        self.requested_message = {}

    @pycog.subcommand("voicemod", independent=True)
    @commands.slash_command(name="claim", description="Claim this channel to moderate it")
    async def claim(self, ctx: discord.ApplicationContext):
        if isinstance(ctx.channel, discord.VoiceChannel):
            try:
                guild_claim = self.claimed[ctx.channel_id]
                await ctx.response.send_message(
                    f"This channel is already claimed by {guild_claim.display_name}", ephemeral=True, delete_after=5.0
                )
            except KeyError:
                if ctx.user in ctx.channel.members:
                    self.claimed[ctx.channel_id] = ctx.user
                    await ctx.response.send_message("You claimed this channel", ephemeral=True, delete_after=5.0)
                else:
                    await ctx.response.send_message(
                        "You cant claim a channel without being in it", ephemeral=True, delete_after=5.0
                    )
        else:
            await ctx.response.send_message("This is not a voice channel", ephemeral=True, delete_after=5.0)

    @pycog.subcommand("voicemod", independent=True)
    @commands.slash_command(name="unclaim", description="Unclaims the channel")
    async def unclaim(self, ctx: discord.ApplicationContext):
        if isinstance(ctx.channel, discord.VoiceChannel):
            try:
                user_claim = self.claimed[ctx.channel_id]
                join2create = await self.client.db.get_temp_voice(ctx.channel)
                is_channel_owner = False
                if join2create is not None:
                    is_channel_owner = join2create.owner_id == ctx.user.id
                if user_claim == ctx.user or ctx.user.guild_permissions.administrator or is_channel_owner:
                    del self.claimed[ctx.channel_id]
                    try:
                        await self.requested_message[ctx.channel_id].delete_original_message()
                        del self.requested_message[ctx.channel_id]
                    except KeyError:
                        pass
                    for member in ctx.channel.members:
                        if member.bot:
                            continue
                        await member.edit(deafen=False, mute=False)
                    await ctx.response.send_message("You unclaimed this channel", ephemeral=True, delete_after=5.0)
                else:
                    await ctx.response.send_message(
                        "Only the owner or an admin can unclaim the channel", ephemeral=True, delete_after=5.0
                    )
            except KeyError:
                await ctx.response.send_message("Channel is unclaimed", ephemeral=True, delete_after=5.0)
        else:
            await ctx.response.send_message("This is not a voice channel", ephemeral=True, delete_after=5.0)

    @pycog.subcommand("voicemod", independent=True)
    @commands.slash_command(name="moderate", description="moderate user in this channel")
    async def moderate(self, ctx: discord.ApplicationContext):
        if isinstance(ctx.channel, discord.VoiceChannel):
            try:
                user_claim = self.claimed[ctx.channel_id]
                if user_claim == ctx.user or ctx.user.guild_permissions.administrator:
                    try:
                        await self.requested_message[ctx.channel_id].delete_original_message()
                        message = await ctx.respond(view=MuteView(ctx.channel), ephemeral=True)
                        self.requested_message[ctx.channel_id] = message
                    except KeyError:
                        message = await ctx.respond(view=MuteView(ctx.channel), ephemeral=True)
                        self.requested_message[ctx.channel_id] = message
                else:
                    await ctx.response.send_message(
                        "You are not the owner of this channel", ephemeral=True, delete_after=5.0
                    )
            except KeyError:
                await ctx.response.send_message(
                    f"Channel is unclaimed. \nClaim this channel by using the {self.claim.mention} command",
                    ephemeral=True,
                    delete_after=5.0,
                )
        else:
            await ctx.response.send_message("This is not a voice channel", ephemeral=True, delete_after=5.0)

    @commands.Cog.listener("on_voice_state_update")
    async def channel_left(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """
        This function removes the server applied mute and deafen, as soon as they join any channel with this status.
        Additionaly if the owner leaves the channel, the channel becomes unclaimed and the server applied mute and deafen are removed.
        """
        if after.channel is not None:
            if before.channel != after.channel:
                if not member.bot:
                    await member.edit(deafen=False, mute=False)

        if before.channel is not None:
            if before.channel.id in [*self.claimed]:
                if member.id == self.claimed[before.channel.id].id and before.channel != after.channel:
                    del self.claimed[before.channel.id]
                    try:
                        try:
                            await self.requested_message[before.channel.id].delete_original_message()
                        except discord.NotFound:
                            pass
                        del self.requested_message[before.channel.id]
                    except KeyError:
                        pass
                    for member in before.channel.members:
                        if member.bot:
                            continue
                        await member.edit(deafen=False, mute=False)

        # Edit the moderation message when someone enters the channel
        if after.channel is not None:
            try:
                message = self.requested_message[after.channel.id]
                await message.edit(view=MuteView(after.channel))
            except KeyError:
                pass

        # Edit the moderation message when someone leaves the channel
        if before.channel is not None:
            try:
                message = self.requested_message[before.channel.id]
                await message.edit(view=MuteView(before.channel))
            except KeyError:
                pass


def setup(client: Bot):
    client.add_cog(InVoiceModeration(client))
