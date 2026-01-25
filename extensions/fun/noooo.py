import discord
from discord.ext import commands
import aiohttp

from utils import Bot, CustomLogger, is_team


class Noooo(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)
    

    @commands.slash_command(name="noooo", description="Sends a kind decline message to the designated user")
    @discord.option(
        "who",
        description="Who to send a kind no",
        required=True,
        input_type=discord.SlashCommandOptionType.mentionable,
    )
    async def noooo(self, ctx: discord.ApplicationContext, who: discord.User):
        async with aiohttp.ClientSession() as session:
            async with session.get("https://naas.isalman.dev/no") as response:
                html = await response.json()
                em = discord.Embed(title="Kind Declination", color=discord.Color.brand_green())
                em.add_field(name="",value=html["reason"])
                em.set_author(name=ctx.author, icon_url=ctx.author.avatar)
                await who.send(
                    embed=em
                )
                em = discord.Embed(title="Kind Declination delivered", color=discord.Color.brand_green())
                em.add_field(name="",value=html["reason"])
                await ctx.response.send_message(embed=em, ephemeral=True)

def setup(client):
    client.add_cog(Noooo(client))
