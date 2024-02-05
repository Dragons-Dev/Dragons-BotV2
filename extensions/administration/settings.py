import discord
from discord.ext import commands

from utils import Bot, CustomLogger, SettingsEnum


def setting_choices(ctx: discord.AutocompleteContext) -> list[str]:
    """Displays every setting from utils/enums.py"""
    settings = []
    for setting in SettingsEnum:
        settings.append(setting.value)
    return sorted(settings)


def value_choices(ctx: discord.AutocompleteContext) -> list[str]:
    """Responds with every Role or Channel depending on the setting and searched term"""
    values = []
    entered = ctx.value
    setting: str = ctx.options.items().mapping["setting"]
    if setting is None:
        return ["Please select a setting first"]
    elif setting.endswith("Role"):
        for role in ctx.interaction.guild.roles:
            if entered in role.name:
                values.append(role.name)
        return values
    elif setting.endswith("Channel"):
        for channel in ctx.interaction.guild.channels:
            if entered in channel.name:
                values.append(channel.name)
        return values
    else:
        return ["A super rare bug appeared and I don't know why!"]


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
            autocomplete=value_choices,
            name="value",
            description="The value you want to set the setting to.",
            required=True,
        ),
    ):
        db_setting = SettingsEnum(setting)
        if db_setting.value.endswith("Role"):
            settings_value = discord.utils.find(lambda c: c.name == value, ctx.guild.roles)
        else:
            settings_value = discord.utils.find(lambda c: c.name == value, ctx.guild.channels)
        await self.client.db.update_setting(setting=db_setting, value=settings_value.id, guild=ctx.guild)

        await ctx.response.send_message(
            embed=discord.Embed(
                title="Success",
                description=f"Changed {setting} to {settings_value.mention}!",
                color=discord.Color.brand_green(),
            ),
            ephemeral=True,
        )


def setup(client):
    client.add_cog(SettingsCog(client))
