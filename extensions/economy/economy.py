import random
import time

import discord
from discord.ext import commands
from pycord import multicog as pycog

from utils import Bot, CustomLogger, is_team

from .models import format_scales, get_guild_id
from .repository import EconomyRepository

__all__ = ["Economy", "setup"]


class Economy(commands.Cog):
    """Cog handling the Dragon Scales economy system."""

    MESSAGE_COOLDOWN_SECONDS: float = 60.0
    VOICE_RATE_PER_HOUR: float = 5.0

    def __init__(self, client: Bot, economy_repo: EconomyRepository | None = None):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)
        self.economy_repo = economy_repo or EconomyRepository(self.client.db.session_maker)
        self._last_message_time: dict[tuple[int, int], float] = {}
        self._last_message_content: dict[tuple[int, int], str] = {}
        self._voice_cache: dict[tuple[int, int], float] = {}

    def _should_ignore_message(self, msg: discord.Message) -> bool:
        if msg.author.bot or not msg.guild:
            return True
        if len(msg.content.strip()) < 3:
            return True
        return False

    def _is_message_spam(self, guild_id: int, user_id: int, content: str, now: float) -> bool:
        key = (guild_id, user_id)
        cleaned = content.strip().lower()
        if self._last_message_content.get(key) == cleaned:
            return True
        last_time = self._last_message_time.get(key)
        if last_time is not None and (now - last_time) < self.MESSAGE_COOLDOWN_SECONDS:
            return True
        return False

    @commands.Cog.listener("on_message")
    async def on_message(self, msg: discord.Message) -> None:
        if self._should_ignore_message(msg):
            return

        guild_id = msg.guild.id  # type: ignore[union-attr]
        user_id = msg.author.id
        now = time.monotonic()

        if self._is_message_spam(guild_id, user_id, msg.content, now):
            return

        key = (guild_id, user_id)
        self._last_message_time[key] = now
        self._last_message_content[key] = msg.content.strip().lower()

        if random.randint(0, 1) == 1:
            await self.economy_repo.add_balance(user_id, guild_id, 1)

    def _is_valid_voice_state(self, member: discord.Member, state: discord.VoiceState | None) -> bool:
        if member.bot or state is None or state.channel is None:
            return False
        guild = state.channel.guild
        if guild.afk_channel and state.channel.id == guild.afk_channel.id:
            return False
        if state.self_deaf or state.deaf:
            return False
        return True

    def _calculate_voice_scales(self, elapsed_seconds: float) -> int:
        return round(elapsed_seconds * self.VOICE_RATE_PER_HOUR / 3600)

    async def _credit_voice_time(self, user_id: int, guild_id: int, now: float) -> int:
        key = (guild_id, user_id)
        start_time = self._voice_cache.get(key)
        if start_time is None:
            return 0
        elapsed = max(0.0, now - start_time)
        scales = self._calculate_voice_scales(elapsed)
        if scales > 0:
            await self.economy_repo.add_balance(user_id, guild_id, scales)
        self._voice_cache.pop(key, None)
        return scales

    def _register_voice_member(self, member: discord.Member, guild: discord.Guild, now: float) -> None:
        if member.bot or not member.voice:
            return
        if member.voice.self_deaf or member.voice.deaf:
            return
        key = (guild.id, member.id)
        if key not in self._voice_cache:
            self._voice_cache[key] = now

    @commands.Cog.listener("on_start_done")
    async def on_start_done(self) -> None:
        now = time.monotonic()
        for guild in self.client.guilds:
            for channel in guild.voice_channels:
                if guild.afk_channel and channel.id == guild.afk_channel.id:
                    continue
                for member in channel.members:
                    self._register_voice_member(member, guild, now)

    @commands.Cog.listener("on_voice_state_update")
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ) -> None:
        if member.bot:
            return

        now = time.monotonic()
        before_valid = self._is_valid_voice_state(member, before)
        after_valid = self._is_valid_voice_state(member, after)

        switched_guild = (
            before.channel is not None
            and after.channel is not None
            and before.channel.guild.id != after.channel.guild.id
        )

        if before_valid and (not after_valid or switched_guild):
            guild_id = before.channel.guild.id  # type: ignore[union-attr]
            await self._credit_voice_time(member.id, guild_id, now)

        if after_valid:
            after_guild_id = after.channel.guild.id  # type: ignore[union-attr]
            after_key = (after_guild_id, member.id)
            if after_key not in self._voice_cache:
                self._voice_cache[after_key] = now

    @pycog.subcommand("economy")
    @commands.slash_command(name="balance", description="View your or another member's Dragon Scales balance.")
    @discord.option(
        "member",
        description="The member to view balance for (defaults to yourself)",
        required=False,
        input_type=discord.Member,
    )
    async def balance(self, ctx: discord.ApplicationContext, member: discord.Member | None = None) -> None:
        target = member or ctx.author
        guild_id = get_guild_id(ctx)
        bal = await self.economy_repo.get_balance(target.id, guild_id)
        embed = discord.Embed(
            title="Dragon Scales Balance",
            description=f"{target.mention} has **{format_scales(bal, ctx.guild, self.client)}**.",
            color=discord.Color.gold(),
        )
        await ctx.response.send_message(embed=embed, ephemeral=True)

    @pycog.subcommand("economy")
    @commands.slash_command(name="pay", description="Pay Dragon Scales to another member.")
    @discord.option(
        "member",
        description="The member to transfer Dragon Scales to",
        required=True,
        input_type=discord.Member,
    )
    @discord.option(
        "amount",
        description="The amount of Dragon Scales to transfer",
        required=True,
        input_type=int,
        min_value=1,
    )
    async def pay(self, ctx: discord.ApplicationContext, member: discord.Member, amount: int) -> None:
        if member.bot:
            await ctx.response.send_message("You cannot transfer Dragon Scales to a bot.", ephemeral=True)
            return
        if member.id == ctx.author.id:
            await ctx.response.send_message("You cannot transfer Dragon Scales to yourself.", ephemeral=True)
            return
        if amount <= 0:
            await ctx.response.send_message("The transfer amount must be greater than 0.", ephemeral=True)
            return

        guild_id = get_guild_id(ctx)
        success = await self.economy_repo.transfer_balance(ctx.author.id, member.id, guild_id, amount)
        if not success:
            bal = await self.economy_repo.get_balance(ctx.author.id, guild_id)
            await ctx.response.send_message(
                f"You do not have enough Dragon Scales. "
                f"Your current balance is {format_scales(bal, ctx.guild, self.client)}.",
                ephemeral=True,
            )
            return

        await ctx.response.send_message(
            f"Successfully transferred {format_scales(amount, ctx.guild, self.client)} to {member.mention}!"
        )

    @pycog.subcommand("economy")
    @commands.slash_command(name="leaderboard", description="View the top 10 richest members in the guild.")
    async def leaderboard(self, ctx: discord.ApplicationContext) -> None:
        guild_id = get_guild_id(ctx)
        leaders = await self.economy_repo.get_leaderboard(guild_id, limit=10)
        if not leaders:
            await ctx.response.send_message("No members have any Dragon Scales yet.", ephemeral=True)
            return

        lines = [
            f"**#{idx}** <@{wallet.user_id}> — {format_scales(wallet.balance, ctx.guild, self.client)}"
            for idx, wallet in enumerate(leaders, start=1)
        ]
        embed = discord.Embed(
            title="Dragon Scales Leaderboard",
            description="\n".join(lines),
            color=discord.Color.gold(),
        )
        await ctx.response.send_message(embed=embed, ephemeral=True)

    @pycog.subcommand("economy")
    @commands.slash_command(name="give", description="Give Dragon Scales to a member.")
    @is_team()
    @discord.option(
        "member",
        description="The member to give Dragon Scales to",
        required=True,
        input_type=discord.Member,
    )
    @discord.option(
        "amount",
        description="The amount of Dragon Scales to give",
        required=True,
        input_type=int,
        min_value=1,
    )
    async def give(self, ctx: discord.ApplicationContext, member: discord.Member, amount: int) -> None:
        if amount <= 0:
            await ctx.response.send_message("The amount must be greater than 0.", ephemeral=True)
            return

        guild_id = get_guild_id(ctx)
        new_bal = await self.economy_repo.add_balance(member.id, guild_id, amount)
        await ctx.response.send_message(
            f"Added {format_scales(amount, ctx.guild, self.client)} to {member.mention}. "
            f"New balance: {format_scales(new_bal, ctx.guild, self.client)}.",
            ephemeral=True,
        )

    @pycog.subcommand("economy")
    @commands.slash_command(name="take", description="Take Dragon Scales from a member.")
    @is_team()
    @discord.option(
        "member",
        description="The member to take Dragon Scales from",
        required=True,
        input_type=discord.Member,
    )
    @discord.option(
        "amount",
        description="The amount of Dragon Scales to take",
        required=True,
        input_type=int,
        min_value=1,
    )
    async def take(self, ctx: discord.ApplicationContext, member: discord.Member, amount: int) -> None:
        if amount <= 0:
            await ctx.response.send_message("The amount must be greater than 0.", ephemeral=True)
            return

        guild_id = get_guild_id(ctx)
        success = await self.economy_repo.remove_balance(member.id, guild_id, amount)
        if not success:
            bal = await self.economy_repo.get_balance(member.id, guild_id)
            await ctx.response.send_message(
                f"Cannot take {format_scales(amount, ctx.guild, self.client)} from {member.mention}. "
                f"Current balance: {format_scales(bal, ctx.guild, self.client)}.",
                ephemeral=True,
            )
            return

        new_bal = await self.economy_repo.get_balance(member.id, guild_id)
        await ctx.response.send_message(
            f"Took {format_scales(amount, ctx.guild, self.client)} from {member.mention}. "
            f"New balance: {format_scales(new_bal, ctx.guild, self.client)}.",
            ephemeral=True,
        )

    @pycog.subcommand("economy")
    @commands.slash_command(name="set", description="Set a member's Dragon Scales balance.")
    @is_team()
    @discord.option(
        "member",
        description="The member whose balance to set",
        required=True,
        input_type=discord.Member,
    )
    @discord.option(
        "amount",
        description="The new balance for the member",
        required=True,
        input_type=int,
        min_value=0,
    )
    async def set_balance(self, ctx: discord.ApplicationContext, member: discord.Member, amount: int) -> None:
        if amount < 0:
            await ctx.response.send_message("The amount cannot be negative.", ephemeral=True)
            return

        guild_id = get_guild_id(ctx)
        new_bal = await self.economy_repo.set_balance(member.id, guild_id, amount)
        await ctx.response.send_message(
            f"Set balance of {member.mention} to {format_scales(new_bal, ctx.guild, self.client)}.",
            ephemeral=True,
        )


def setup(client: Bot) -> None:
    client.add_cog(Economy(client))
