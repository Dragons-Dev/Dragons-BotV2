import discord
from discord.ext import commands

from utils import Bot, CustomLogger, SettingsEnum, checks, is_team


def setting_choices(ctx: discord.AutocompleteContext) -> list[str]:
    """Supplies every setting from utils/enums.py for commands

    Args:
        ctx (discord.AutocompleteContext):

    Returns:
        list[str]: every setting from utils/enums.py
    """
    settings = []
    for setting in SettingsEnum:
        settings.append(setting.value)
    return sorted(settings)


def value_choices(ctx: discord.AutocompleteContext) -> list[str]:
    """Responds with every Role or Channel depending on the setting and searched term

    Args:
        ctx (discord.AutocompleteContext):

    Returns:
        list[str]: Role or Channel names depending on the searched term
    """
    values = []
    entered = ctx.value
    bot: Bot = ctx.bot
    setting: str = ctx.options.items().mapping["setting"]  # access the setting
    if setting is None:
        return ["Please select a setting first"]
    elif setting.endswith("Role"):
        values.append("❌ Remove Setting ❌")
        for role in ctx.interaction.guild.roles:
            if entered in role.name:
                values.append(role.name)
        return values
    elif setting.endswith("Channel"):
        values.append("❌ Remove Setting ❌")
        for channel in ctx.interaction.guild.channels:
            if entered in channel.name:
                values.append(channel.name)
        return values
    else:
        bot.logger.error(f"No value could be found for setting {setting}")
        return ["A super rare bug appeared and I don't know why!"]


class SettingsCog(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)

    @commands.slash_command(
        name="setting", description="Set settings for this guild.", contexts={discord.InteractionContextType.guild}
    )
    @commands.check_any(checks.is_team(), commands.has_guild_permissions(administrator=True))
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
        if value == "❌ Remove Setting ❌":
            await self.client.db.delete_setting(db_setting, ctx.guild)
            return await ctx.response.send_message(
                embed=discord.Embed(
                    title="Success",
                    description=f"Removed {setting}!",
                    color=discord.Color.brand_green(),
                ),
                ephemeral=True,
            )
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

    @commands.slash_command(name="settings_show", description="show's the currently set settings",
                            contexts={discord.InteractionContextType.guild})
    @is_team()
    async def settings_show(self, ctx: discord.ApplicationContext):
        embed = discord.Embed(title="Guild Settings", color=discord.Color.dark_orange())
        for enum_value in SettingsEnum:
            enum = SettingsEnum(enum_value)
            setting_value = await self.client.db.get_setting(setting=enum, guild=ctx.guild)
            if setting_value is None:
                pass
            else:
                embed.add_field(
                    name=enum.value,
                    value=f"<@&{setting_value}>" if enum.value.endswith("Role") else f"<#{setting_value}>",
                    inline=True,
                )
        if len(embed.fields) == 0:
            embed.description = f"No settings are set, use {self.setting.mention} to set some!"
        await ctx.response.send_message(embed=embed, ephemeral=True)


def setup(client):
    client.add_cog(SettingsCog(client))
