from collections.abc import Sequence

import discord
from discord.ext import commands
from discord.utils import format_dt
from pycord import multicog as pycog

from utils import Bot, CustomLogger, StatTypeEnum, sec_to_readable, SettingsEnum, ContainerPaginator
from utils.orm_database import Infractions


def _build_infraction_container(
    inf_member: discord.User | discord.Member, infraction: Infractions | Sequence[Infractions]
) -> discord.ui.DesignerView | ContainerPaginator:
    container = discord.ui.Container(color=discord.Color.brand_red())
    container.add_text(f"## Infraction for {inf_member.global_name or inf_member.name}")
    if isinstance(infraction, Infractions):
        container.add_text(
            f"**Case ID:** {infraction.case_id}\n"
            f"**Infraction:** {infraction.infraction}\n"
            f"**Reason:** {infraction.reason}\n"
            f"**Date:** {format_dt(infraction.date, style='D')}\n"
        )
        return discord.ui.DesignerView(container)
    else:
        paginator = ContainerPaginator()
        pages_required = (len(infraction) + 4) // 5  # Show 5 infractions per page
        for i in range(pages_required):
            page_container = discord.ui.Container(color=discord.Color.brand_red())
            page_container.add_text(f"## Infractions for {inf_member.global_name or inf_member.name}")
            for inf in infraction[i * 5 : (i + 1) * 5]:
                page_container.add_text(
                    f"**Case ID:** {inf.case_id}\n"
                    f"**Infraction:** {inf.infraction}\n"
                    f"**Reason:** {inf.reason}\n"
                    f"**Date:** {format_dt(inf.date, style='D')}\n"
                )
            paginator.add_page(page_container)
        return paginator


class InfractionButton(discord.ui.Button):
    def __init__(self, client: Bot, target: discord.Member):
        self.client = client
        self.target = target
        super().__init__(label="View Infraction", style=discord.ButtonStyle.red)

    async def callback(self, interaction: discord.Interaction):
        # Fetch the infraction details from the database using the infraction_id
        infraction = await self.client.db.get_infraction(None, self.target, self.target.guild)
        container_or_view = _build_infraction_container(self.target, infraction)
        if isinstance(container_or_view, ContainerPaginator):
            view = container_or_view.update_view()
        else:
            view = container_or_view
        await interaction.response.send_message(view=view, ephemeral=True)


class UserInfo(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)

    @pycog.subcommand("user")
    @commands.slash_command(
        name="info",
        description="Get information about yourself or someone else.",
    )
    @discord.option(
        "member",
        description="The member to get information about.",
        required=False,
        input_type=discord.Member,
        parameter_name="cmd_member",
    )
    async def slash_test_command(self, ctx: discord.ApplicationContext, cmd_member: discord.Member | None = None):
        target = cmd_member or ctx.author  # If no member is provided, use the command author as the target
        member = await ctx.guild.get_or_fetch(discord.Member, target.id, None)  # get the member object to cache
        team_role = await self.client.db.get_setting(SettingsEnum.TeamRole, ctx.guild)

        container = discord.ui.Container()
        container.add_section(
            discord.ui.TextDisplay(content=f"## {member.global_name or member.name} Overview"),
            accessory=discord.ui.Thumbnail(
                url=(member.avatar or member.default_avatar).url,
            ),
        )

        if (
            ctx.author == target
            or ((0 if not team_role else team_role.value) in [r.id for r in member.roles])
            or ctx.author.guild_permissions.administrator
            or ctx.author.guild_permissions.manage_guild
        ):
            container.add_separator()
            # Database calls
            voice_time = await self.client.db.get_user_stat_total(target, StatTypeEnum.VoiceTime, ctx.guild)
            messages_sent = await self.client.db.get_user_stat_total(target, StatTypeEnum.MessagesSent, ctx.guild)
            commands_used = await self.client.db.get_user_stat_total(target, StatTypeEnum.CommandsUsed, ctx.guild)
            infractions = await self.client.db.get_infraction(None, target, ctx.guild)
            container.add_text(
                f"Voice time 🎤: {sec_to_readable(voice_time or '0')}\n"
                f"Messages sent 💬: {messages_sent or '0'}\n"
                f"Commands used ⚡: {commands_used or '0'}\n"
                f"Infractions 🚨: {len(infractions) if infractions else '0'}"
            )
            if infractions:
                container.add_section(
                    discord.ui.TextDisplay(content="See all infractions for this user"),
                    accessory=InfractionButton(client=self.client, target=target),
                )
        container.add_text(
            f"User: {member.mention}\n"
            f"User ID: {member.id}\n"
            f"Top Role: {member.top_role.mention}\n"
            f"Joined server on: {format_dt(member.joined_at, style='D')}\n"
            f"Account created on: {format_dt(member.created_at, style='D')}"
        )

        await ctx.response.send_message(view=discord.ui.DesignerView(container), ephemeral=True)


def setup(client):
    client.add_cog(UserInfo(client))
