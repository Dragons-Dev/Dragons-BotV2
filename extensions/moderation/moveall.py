import asyncio

import discord
from discord.ext import commands
import pycord.multicog as pycog

from utils import Bot, CustomLogger, SettingsEnum


async def _send_ephemeral(ctx: discord.ApplicationContext, content: str) -> None:
    if ctx.response.is_done():
        await ctx.followup.send(content, ephemeral=True)
    else:
        await ctx.response.send_message(content, ephemeral=True)


async def _has_team_role(client: Bot, ctx: discord.ApplicationContext, author: discord.Member) -> bool:
    if ctx.guild is None or getattr(client, "db", None) is None:
        return False
    try:
        team_role = await client.db.get_setting(setting=SettingsEnum.TeamRole, guild=ctx.guild)
        role_id = getattr(team_role, "value", None)
        if role_id is not None:
            return any(getattr(r, "id", None) == role_id for r in getattr(author, "roles", []))
    except Exception:
        pass
    return False


async def _is_caller_authorized(
    client: Bot,
    ctx: discord.ApplicationContext,
    source: discord.VoiceChannel,
    destination: discord.VoiceChannel,
) -> bool:
    author = ctx.author
    guild_perms = getattr(author, "guild_permissions", None)
    if guild_perms and guild_perms.administrator:
        return True

    source_perms = source.permissions_for(author)
    dest_perms = destination.permissions_for(author)
    if source_perms.move_members and dest_perms.move_members:
        return True

    return await _has_team_role(client, ctx, author)


def _has_bot_permissions(
    ctx: discord.ApplicationContext,
    source: discord.VoiceChannel,
    destination: discord.VoiceChannel,
) -> bool:
    if ctx.guild is None or ctx.guild.me is None:
        return False
    bot_member = ctx.guild.me
    source_perms = source.permissions_for(bot_member)
    dest_perms = destination.permissions_for(bot_member)
    return bool(source_perms.move_members and dest_perms.move_members and dest_perms.connect)


async def _execute_mass_move(
    ctx: discord.ApplicationContext,
    destination: discord.VoiceChannel,
    members_to_move: list[discord.Member],
) -> int:
    moved_count = 0
    total = len(members_to_move)
    for index, member in enumerate(members_to_move):
        try:
            await member.move_to(destination, reason=f"Mass move by {ctx.author}")
            moved_count += 1
        except (discord.Forbidden, discord.HTTPException):
            pass
        if index < total - 1:
            await asyncio.sleep(0.15)
    return moved_count


class MoveAll(commands.Cog):
    def __init__(self, client: Bot):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)

    @pycog.subcommand("mod")
    @commands.slash_command(name="moveall", description="Move all members from one voice channel to another")
    @discord.guild_only()
    @discord.option(
        "source",
        description="The voice channel to move members from",
        input_type=discord.VoiceChannel,
        required=True,
    )
    @discord.option(
        "destination",
        description="The voice channel to move members to",
        input_type=discord.VoiceChannel,
        required=True,
    )
    async def moveall(
        self,
        ctx: discord.ApplicationContext,
        source: discord.VoiceChannel,
        destination: discord.VoiceChannel,
    ):
        if source.id == destination.id:
            await _send_ephemeral(ctx, "Source and destination channels must not be identical.")
            return

        if not await _is_caller_authorized(self.client, ctx, source, destination):
            await _send_ephemeral(ctx, "You do not have permission to move members between these channels.")
            return

        if not _has_bot_permissions(ctx, source, destination):
            await _send_ephemeral(ctx, "I lack Move Members or Connect permissions for the channels.")
            return

        if len(source.members) == 0:
            await _send_ephemeral(ctx, "There are currently no members in the source channel.")
            return

        await ctx.response.defer(ephemeral=True)

        members_to_move = list(source.members)
        moved_count = await _execute_mass_move(ctx, destination, members_to_move)

        member_word = "member" if moved_count == 1 else "members"
        await ctx.followup.send(
            f"Successfully moved {moved_count} {member_word} from {source.mention} to {destination.mention}.",
            ephemeral=True,
        )


def setup(client: Bot):
    client.add_cog(MoveAll(client))
