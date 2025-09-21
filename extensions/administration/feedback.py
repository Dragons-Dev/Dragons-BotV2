import discord
from discord.ext import commands
from discord.utils import get_or_fetch

from utils import Bot, ButtonInfo, CustomLogger, SettingsEnum


class FeedbackModal(discord.ui.Modal):
    def __init__(self, guild: discord.Guild, client: Bot, *args, **kwargs) -> None:
        self.guild: discord.Guild = guild
        self.client: Bot = client
        super().__init__(*args, **kwargs)
        self.add_item(
            discord.ui.InputText(
                label="Ignore me",
                style=discord.InputTextStyle.short,
                value="Your feedback will be sent anonymous. This is useless if you share personal information.",
                required=False,
            )
        )
        self.add_item(
            discord.ui.InputText(
                label="Feedback", placeholder="Write your feedback here!", style=discord.InputTextStyle.long
            )
        )

    async def callback(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Feedback",
            description=self.children[1].value,
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(
            embeds=[embed], ephemeral=True, view=ButtonInfo("The embed you are seeing is sent to the administrators.")
        )
        feedback_id = await self.client.db.get_setting(SettingsEnum.FeedbackChannel, interaction.guild)
        if feedback_id:
            feedback_channel = await get_or_fetch(interaction.guild, "channel", feedback_id.value, default=None)
            await feedback_channel.send(embeds=[embed])


class Feedback(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)

    @commands.slash_command(name="feedback", description="Send feedback to the discord guild.")
    async def feedback(self, ctx: discord.ApplicationContext):
        await ctx.response.send_modal(FeedbackModal(ctx.guild, self.client, title="Feedback Modal"))


def setup(client):
    client.add_cog(Feedback(client))
