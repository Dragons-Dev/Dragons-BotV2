import discord
from discord.ext import commands

from utils import Bot, CustomLogger, SettingsEnum


def setting_choices(ctx: discord.AutocompleteContext) -> list[str]:
    settings = []
    for setting in SettingsEnum:
        settings.append(setting.value)
    return settings


class SettingsCog(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot)

    @commands.slash_command(name="setting", description="Set settings for this guild.")
    async def setting(
        self,
        ctx: discord.ApplicationContext,
        setting: discord.Option(  # type: ignore
            autocomplete=setting_choices,
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
        if db_setting == SettingsEnum.TeamRole or db_setting == SettingsEnum.VerifiedRole:
            value = f"<@&{db_value}>"
        else:
            value = f"<#{db_value}>"
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
