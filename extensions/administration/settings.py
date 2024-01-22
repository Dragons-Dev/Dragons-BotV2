import discord
from discord.ext import commands

from utils import Bot, CustomLogger, SettingsEnum

SettingChoices = [
    discord.OptionChoice("Team Role"),
    discord.OptionChoice("Verified Role"),
    discord.OptionChoice("Mod-Log Channel"),
    discord.OptionChoice("Modmail Channel"),
    discord.OptionChoice("Verification Channel"),
    discord.OptionChoice("Join2Create Channel"),
]


class SettingsCog(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot)

    @commands.slash_command(name="setting", description="Set settings for this guild.")
    async def setting(
        self,
        ctx: discord.ApplicationContext,
        setting: discord.Option(  # type: ignore
            choices=SettingChoices,
            name="setting",
            description="Select the setting you want to change in this guild.",
            required=True,
        ),  # ignoring those two @mypy because it's the intended behavior by the library
        value: discord.Option(  # type: ignore
            input_type=discord.SlashCommandOptionType.mentionable,
            name="value",
            description="The value you want to set the setting to.",
            required=True,
        ),
    ):
        db_setting = SettingsEnum(setting)
        db_value = value.strip("<@&#>")
        await self.client.db.update_setting(setting=db_setting, value=db_value, guild=ctx.guild)
        await ctx.response.send_message(
            embed=discord.Embed(
                title="Success",
                description=f"Changed {setting} to {value}!",
                color=discord.Color.brand_green(),
            ),
            ephemeral=True,
        )


def setup(client):
    client.add_cog(SettingsCog(client))
