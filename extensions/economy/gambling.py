import random
from typing import Literal

import discord
from discord.ext import commands
from pycord import multicog as pycog

from utils import Bot, CustomLogger
from utils.enums import SettingsEnum

from .models import BetPool, format_scales
from .repository import EconomyRepository, GamblingRepository

__all__ = ["Gambling", "setup"]

SLOT_SYMBOLS = ["🍒", "🍋", "🔔", "💎", "🐉"]


def _calculate_slot_multiplier(symbols: list[str]) -> int:
    s1, s2, s3 = symbols
    if s1 == s2 == s3:
        return 10 if s1 == "🐉" else 5
    if s1 == s2 or s2 == s3 or s1 == s3:
        return 2
    return 0


class Gambling(commands.Cog):
    """Cog handling gambling mini-games and custom prediction bet pools."""

    def __init__(
        self,
        client: Bot,
        gambling_repo: GamblingRepository | None = None,
        economy_repo: EconomyRepository | None = None,
    ):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)
        self.gambling_repo = gambling_repo or GamblingRepository(self.client.db.session_maker)
        self.economy_repo = economy_repo or EconomyRepository(self.client.db.session_maker)

    async def _deduct_or_notify(self, ctx: discord.ApplicationContext, amount: int) -> bool:
        if amount <= 0:
            await ctx.response.send_message("The bet amount must be greater than 0.", ephemeral=True)
            return False
        success = await self.economy_repo.remove_balance(ctx.author.id, ctx.guild.id, amount)
        if not success:
            bal = await self.economy_repo.get_balance(ctx.author.id, ctx.guild.id)
            await ctx.response.send_message(
                f"You do not have enough Dragon Scales. Current balance: {format_scales(bal, ctx.guild)}.",
                ephemeral=True,
            )
            return False
        return True

    @pycog.subcommand("gamble")
    @commands.slash_command(name="coinflip", description="Bet Dragon Scales on a coin flip.")
    @discord.option("choice", input_type=str, description="Heads or tails", choices=["heads", "tails"])
    @discord.option("amount", input_type=int, description="The amount of Dragon Scales to bet", min_value=1)
    async def coinflip(
        self,
        ctx: discord.ApplicationContext,
        choice: Literal["heads", "tails"],
        amount: int,
    ) -> None:
        if not await self._deduct_or_notify(ctx, amount):
            return

        flip = random.choice(["heads", "tails"])
        won = choice.lower() == flip
        if won:
            payout = amount * 2
            await self.economy_repo.add_balance(ctx.author.id, ctx.guild.id, payout)
            new_bal = await self.economy_repo.get_balance(ctx.author.id, ctx.guild.id)
            embed = discord.Embed(
                title="🪙 Coinflip — Winner!",
                description=(
                    f"The coin landed on **{flip}**!\n"
                    f"You won **{format_scales(payout, ctx.guild)}**!\n"
                    f"New balance: {format_scales(new_bal, ctx.guild)}."
                ),
                color=discord.Color.green(),
            )
        else:
            new_bal = await self.economy_repo.get_balance(ctx.author.id, ctx.guild.id)
            embed = discord.Embed(
                title="🪙 Coinflip — Lost",
                description=(
                    f"The coin landed on **{flip}**.\n"
                    f"You lost **{format_scales(amount, ctx.guild)}**.\n"
                    f"New balance: {format_scales(new_bal, ctx.guild)}."
                ),
                color=discord.Color.red(),
            )
        await ctx.response.send_message(embed=embed)

    @pycog.subcommand("gamble")
    @commands.slash_command(name="dice", description="Bet Dragon Scales on a 6-sided dice roll.")
    @discord.option("guess", input_type=int, description="Your dice guess (1 to 6)", min_value=1, max_value=6)
    @discord.option("amount", input_type=int, description="The amount of Dragon Scales to bet", min_value=1)
    async def dice(
        self,
        ctx: discord.ApplicationContext,
        guess: int,
        amount: int,
    ) -> None:
        if not (1 <= guess <= 6):
            await ctx.response.send_message("Your guess must be between 1 and 6.", ephemeral=True)
            return

        if not await self._deduct_or_notify(ctx, amount):
            return

        roll = random.randint(1, 6)
        won = guess == roll
        if won:
            payout = amount * 6
            await self.economy_repo.add_balance(ctx.author.id, ctx.guild.id, payout)
            new_bal = await self.economy_repo.get_balance(ctx.author.id, ctx.guild.id)
            embed = discord.Embed(
                title="🎲 Dice Roll — Winner!",
                description=(
                    f"The die rolled a **{roll}**!\n"
                    f"You won **{format_scales(payout, ctx.guild)}**!\n"
                    f"New balance: {format_scales(new_bal, ctx.guild)}."
                ),
                color=discord.Color.green(),
            )
        else:
            new_bal = await self.economy_repo.get_balance(ctx.author.id, ctx.guild.id)
            embed = discord.Embed(
                title="🎲 Dice Roll — Lost",
                description=(
                    f"The die rolled a **{roll}** (your guess: {guess}).\n"
                    f"You lost **{format_scales(amount, ctx.guild)}**.\n"
                    f"New balance: {format_scales(new_bal, ctx.guild)}."
                ),
                color=discord.Color.red(),
            )
        await ctx.response.send_message(embed=embed)

    @pycog.subcommand("gamble")
    @commands.slash_command(name="slots", description="Bet Dragon Scales on the slot machine.")
    @discord.option("amount", input_type=int, description="The amount of Dragon Scales to bet", min_value=1)
    async def slots(
        self,
        ctx: discord.ApplicationContext,
        amount: int,
    ) -> None:
        if not await self._deduct_or_notify(ctx, amount):
            return

        symbols = random.choices(SLOT_SYMBOLS, k=3)
        multiplier = _calculate_slot_multiplier(symbols)
        slot_display = f"[ {' | '.join(symbols)} ]"

        if multiplier > 0:
            payout = amount * multiplier
            await self.economy_repo.add_balance(ctx.author.id, ctx.guild.id, payout)
            new_bal = await self.economy_repo.get_balance(ctx.author.id, ctx.guild.id)
            embed = discord.Embed(
                title="🎰 Slots — Winner!",
                description=(
                    f"**{slot_display}**\n\n"
                    f"Multiplier: **{multiplier}x**!\n"
                    f"You won **{format_scales(payout, ctx.guild)}**!\n"
                    f"New balance: {format_scales(new_bal, ctx.guild)}."
                ),
                color=discord.Color.green(),
            )
        else:
            new_bal = await self.economy_repo.get_balance(ctx.author.id, ctx.guild.id)
            embed = discord.Embed(
                title="🎰 Slots — Lost",
                description=(
                    f"**{slot_display}**\n\n"
                    "No matching symbols.\n"
                    f"You lost **{format_scales(amount, ctx.guild)}**.\n"
                    f"New balance: {format_scales(new_bal, ctx.guild)}."
                ),
                color=discord.Color.red(),
            )
        await ctx.response.send_message(embed=embed)

    @pycog.subcommand("gamble")
    @commands.slash_command(name="bet_create", description="Create a new prediction bet pool.")
    @discord.option("title", input_type=str, description="The question or title of the bet")
    @discord.option("option_a", input_type=str, description="First outcome option")
    @discord.option("option_b", input_type=str, description="Second outcome option")
    async def bet_create(
        self,
        ctx: discord.ApplicationContext,
        title: str,
        option_a: str,
        option_b: str,
    ) -> None:
        clean_title = title.strip()
        clean_a = option_a.strip()
        clean_b = option_b.strip()
        if not clean_title or not clean_a or not clean_b:
            await ctx.response.send_message("Title and options cannot be empty.", ephemeral=True)
            return

        pool = await self.gambling_repo.create_bet_pool(ctx.guild.id, ctx.author.id, clean_title, clean_a, clean_b)
        embed = discord.Embed(
            title=f"🎲 Bet Pool #{pool.id}: {pool.title}",
            color=discord.Color.gold(),
        )
        embed.add_field(name="Option A", value=pool.option_a, inline=True)
        embed.add_field(name="Option B", value=pool.option_b, inline=True)
        embed.add_field(name="Created By", value=ctx.author.mention, inline=False)
        embed.set_footer(text=f"Use /gamble bet_place bet_id:{pool.id} to place your wager!")
        await ctx.response.send_message(embed=embed)

    async def _handle_bet_place_failure(
        self,
        ctx: discord.ApplicationContext,
        bet_id: int,
        choice: str,
        amount: int,
    ) -> None:
        wagers = await self.gambling_repo.get_pool_wagers(bet_id, ctx.guild.id)
        user_wagers = [w for w in wagers if w.user_id == ctx.author.id]
        if any(w.choice != choice for w in user_wagers):
            await ctx.response.send_message(
                "You have already wagered on the other option for this bet pool.",
                ephemeral=True,
            )
            return

        bal = await self.economy_repo.get_balance(ctx.author.id, ctx.guild.id)
        if bal < amount:
            await ctx.response.send_message(
                f"You do not have enough Dragon Scales. Current balance: {format_scales(bal, ctx.guild)}.",
                ephemeral=True,
            )
            return

        await ctx.response.send_message("Failed to place wager. Please try again.", ephemeral=True)

    @pycog.subcommand("gamble")
    @commands.slash_command(name="bet_place", description="Place a wager on an open bet pool.")
    @discord.option("bet_id", input_type=int, description="The ID of the bet pool", min_value=1)
    @discord.option("choice", input_type=str, description="Option A or B", choices=["A", "B"])
    @discord.option("amount", input_type=int, description="Amount of Dragon Scales to wager", min_value=1)
    async def bet_place(
        self,
        ctx: discord.ApplicationContext,
        bet_id: int,
        choice: Literal["A", "B"],
        amount: int,
    ) -> None:
        normalized_choice = choice.upper()
        if normalized_choice not in ("A", "B"):
            await ctx.response.send_message("Choice must be 'A' or 'B'.", ephemeral=True)
            return
        if amount <= 0:
            await ctx.response.send_message("The wager amount must be greater than 0.", ephemeral=True)
            return

        pool = await self.gambling_repo.get_bet_pool(bet_id, ctx.guild.id)
        if pool is None:
            await ctx.response.send_message(f"Bet pool #{bet_id} does not exist.", ephemeral=True)
            return
        if not pool.is_open:
            await ctx.response.send_message(f"Bet pool #{bet_id} is already closed.", ephemeral=True)
            return

        success = await self.gambling_repo.place_wager(bet_id, ctx.author.id, ctx.guild.id, normalized_choice, amount)
        if not success:
            await self._handle_bet_place_failure(ctx, bet_id, normalized_choice, amount)
            return

        choice_text = pool.option_a if normalized_choice == "A" else pool.option_b
        embed = discord.Embed(
            title="Wager Placed!",
            description=(
                f"Successfully wagered **{format_scales(amount, ctx.guild)}** on "
                f"**Option {normalized_choice}** ({choice_text}) for Bet #{bet_id}."
            ),
            color=discord.Color.blue(),
        )
        await ctx.response.send_message(embed=embed)

    @pycog.subcommand("gamble")
    @commands.slash_command(name="bet_list", description="List all open prediction bet pools.")
    async def bet_list(self, ctx: discord.ApplicationContext) -> None:
        pools = await self.gambling_repo.get_open_bet_pools(ctx.guild.id)
        if not pools:
            await ctx.response.send_message("There are currently no open bet pools in this server.")
            return

        embed = discord.Embed(
            title="Active Prediction Bet Pools",
            color=discord.Color.gold(),
        )
        for pool in pools:
            wagers = await self.gambling_repo.get_pool_wagers(pool.id, ctx.guild.id)
            total_a = sum(w.amount for w in wagers if w.choice == "A")
            total_b = sum(w.amount for w in wagers if w.choice == "B")
            embed.add_field(
                name=f"#{pool.id}: {pool.title}",
                value=(
                    f"• **[A]** {pool.option_a}: {format_scales(total_a, ctx.guild)}\n"
                    f"• **[B]** {pool.option_b}: {format_scales(total_b, ctx.guild)}\n"
                    f"• Total Pool: {format_scales(total_a + total_b, ctx.guild)}"
                ),
                inline=False,
            )
        await ctx.response.send_message(embed=embed)

    async def _is_authorized_resolver(self, ctx: discord.ApplicationContext, creator_id: int) -> bool:
        if ctx.author.id == creator_id:
            return True
        author = ctx.author
        guild_perms = getattr(author, "guild_permissions", None)
        if guild_perms and getattr(guild_perms, "administrator", False):
            return True

        if ctx.guild is not None and hasattr(self.client, "db") and self.client.db:
            team_setting = await self.client.db.get_setting(SettingsEnum.TeamRole, ctx.guild)
            if team_setting is not None:
                role_id = getattr(team_setting, "value", None)
                roles = getattr(author, "roles", [])
                if role_id and any(getattr(r, "id", None) == role_id for r in roles):
                    return True
        return False

    async def _handle_bet_cancel(self, ctx: discord.ApplicationContext, pool: BetPool) -> None:
        success = await self.gambling_repo.cancel_bet_pool(pool.id, ctx.guild.id)
        if not success:
            await ctx.response.send_message(f"Bet pool #{pool.id} could not be cancelled.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"Bet Pool #{pool.id} Cancelled",
            description=f"Bet pool **{pool.title}** has been cancelled.\nAll wagers have been refunded.",
            color=discord.Color.orange(),
        )
        await ctx.response.send_message(embed=embed)

    async def _handle_bet_outcome(self, ctx: discord.ApplicationContext, pool: BetPool, winning_choice: str) -> None:
        payouts = await self.gambling_repo.resolve_bet_pool(pool.id, ctx.guild.id, winning_choice)
        if payouts is None:
            await ctx.response.send_message(f"Bet pool #{pool.id} could not be resolved.", ephemeral=True)
            return

        winning_text = pool.option_a if winning_choice == "A" else pool.option_b
        if not payouts:
            embed = discord.Embed(
                title=f"Bet Pool #{pool.id} Resolved",
                description=(
                    f"Winning Option: **Option {winning_choice} ({winning_text})**\n\n"
                    "No members wagered on the winning option. All wagers have been refunded!"
                ),
                color=discord.Color.gold(),
            )
        else:
            lines = [f"<@{uid}> — **{format_scales(amt, ctx.guild)}**" for uid, amt in payouts.items()]
            embed = discord.Embed(
                title=f"Bet Pool #{pool.id} Resolved",
                description=(
                    f"Winning Option: **Option {winning_choice} ({winning_text})**\n\n"
                    f"**Payouts ({len(payouts)} winners):**\n" + "\n".join(lines)
                ),
                color=discord.Color.green(),
            )
        await ctx.response.send_message(embed=embed)

    @pycog.subcommand("gamble")
    @commands.slash_command(name="bet_resolve", description="Resolve or cancel an open bet pool.")
    @discord.option("bet_id", input_type=int, description="The ID of the bet pool", min_value=1)
    @discord.option(
        "outcome",
        input_type=str,
        description="Winning outcome (A, B, or cancel)",
        choices=["A", "B", "cancel"],
    )
    async def bet_resolve(
        self,
        ctx: discord.ApplicationContext,
        bet_id: int,
        outcome: Literal["A", "B", "cancel"],
    ) -> None:
        pool = await self.gambling_repo.get_bet_pool(bet_id, ctx.guild.id)
        if pool is None:
            await ctx.response.send_message(f"Bet pool #{bet_id} does not exist.", ephemeral=True)
            return
        if not pool.is_open:
            await ctx.response.send_message(f"Bet pool #{bet_id} is already closed.", ephemeral=True)
            return

        if not await self._is_authorized_resolver(ctx, pool.creator_id):
            await ctx.response.send_message(
                "Only the bet creator or a team member can resolve this bet.",
                ephemeral=True,
            )
            return

        if outcome.lower() == "cancel":
            await self._handle_bet_cancel(ctx, pool)
        else:
            await self._handle_bet_outcome(ctx, pool, outcome.upper())


def setup(client: Bot) -> None:
    client.add_cog(Gambling(client))
