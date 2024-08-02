import discord
from discord.ext import commands

from utils import Bot, CustomLogger


class FeedbackModal(discord.ui.Modal):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.add_item(
            discord.ui.InputText(
                style=discord.InputTextStyle.long, label="Your feedback", placeholder="Enter your feedback here"
            )
        )

    async def callback(self, interaction: discord.Interaction):
        embed = discord.Embed(title="Feedback received", description="The second embed is what will be sent to the ")
        preview = discord.Embed(title=self.title, description=self.children[0].value, color=discord.Color.dark_gold())
        await interaction.response.send_message(embeds=[embed, preview])


class Feedback(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)

    @commands.slash_command(name="feedback", description="Send us feedback")
    async def feedback(
        self,
        ctx: discord.ApplicationContext,
        select_option: discord.Option(  # type: ignore
            input_type=str,
            name="receiver",
            description="select the receiver of your feedback",
            required=True,
            choices=[
                discord.OptionChoice(name="Owner", value="Guild Owner"),
                discord.OptionChoice(name="Developer", value="Developer"),
            ],
        ),
    ):
        await ctx.response.send_modal(FeedbackModal(title=f"{select_option} Feedback"))


def setup(client):
    client.add_cog(Feedback(client))
