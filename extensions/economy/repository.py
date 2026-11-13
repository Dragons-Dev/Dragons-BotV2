from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from utils.orm_database.repository import BaseRepository

from .models import MAX_BET_OPTIONS, BetOption, BetPool, BetWager, EconomyWallet

__all__ = ["EconomyRepository", "GamblingRepository"]


class EconomyRepository(BaseRepository):
    """Repository for economy wallet operations."""

    async def get_balance(self, user_id: int, guild_id: int) -> int:
        """
        Get the current balance for a user in a guild.

        :param user_id: The ID of the user.
        :param guild_id: The ID of the guild.
        :return: Current balance (0 if no wallet exists).
        """
        async with self.session() as session:
            stmt = select(EconomyWallet.balance).where(
                EconomyWallet.user_id == user_id,
                EconomyWallet.guild_id == guild_id,
            )
            result = (await session.execute(stmt)).scalar_one_or_none()
            return result if result is not None else 0

    async def add_balance(self, user_id: int, guild_id: int, amount: int) -> int:
        """
        Add Dragon Scales to a user's wallet in a guild.

        :param user_id: The ID of the user.
        :param guild_id: The ID of the guild.
        :param amount: Amount to add (must be >= 0).
        :return: New balance.
        :raises ValueError: If amount is negative.
        """
        if amount < 0:
            raise ValueError("Amount cannot be negative")

        async with self.session() as session:
            stmt = select(EconomyWallet).where(
                EconomyWallet.user_id == user_id,
                EconomyWallet.guild_id == guild_id,
            )
            wallet = (await session.execute(stmt)).scalar_one_or_none()
            if wallet is None:
                wallet = EconomyWallet(user_id=user_id, guild_id=guild_id, balance=amount)
                session.add(wallet)
            else:
                wallet.balance += amount
            return wallet.balance

    async def remove_balance(self, user_id: int, guild_id: int, amount: int) -> bool:
        """
        Atomically remove Dragon Scales from a user's wallet if sufficient funds exist.

        :param user_id: The ID of the user.
        :param guild_id: The ID of the guild.
        :param amount: Amount to remove (must be > 0 to succeed).
        :return: True if deducted successfully, False otherwise without modifying balance.
        :raises ValueError: If amount is negative.
        """
        if amount < 0:
            raise ValueError("Amount cannot be negative")
        if amount == 0:
            return False

        async with self.session() as session:
            stmt = (
                update(EconomyWallet)
                .where(
                    EconomyWallet.user_id == user_id,
                    EconomyWallet.guild_id == guild_id,
                    EconomyWallet.balance >= amount,
                )
                .values(balance=EconomyWallet.balance - amount)
            )
            result = await session.execute(stmt)
            rowcount = getattr(result, "rowcount", 0)
            return bool(rowcount and rowcount > 0)

    async def set_balance(self, user_id: int, guild_id: int, amount: int) -> int:
        """
        Set a user's wallet balance in a guild.

        :param user_id: The ID of the user.
        :param guild_id: The ID of the guild.
        :param amount: New balance (must be >= 0).
        :return: New balance.
        :raises ValueError: If amount is negative.
        """
        if amount < 0:
            raise ValueError("Amount cannot be negative")

        async with self.session() as session:
            stmt = select(EconomyWallet).where(
                EconomyWallet.user_id == user_id,
                EconomyWallet.guild_id == guild_id,
            )
            wallet = (await session.execute(stmt)).scalar_one_or_none()
            if wallet is None:
                wallet = EconomyWallet(user_id=user_id, guild_id=guild_id, balance=amount)
                session.add(wallet)
            else:
                wallet.balance = amount
            return wallet.balance

    async def transfer_balance(self, sender_id: int, receiver_id: int, guild_id: int, amount: int) -> bool:
        """
        Atomically transfer Dragon Scales between two users in the same guild.

        :param sender_id: The ID of the sending user.
        :param receiver_id: The ID of the receiving user.
        :param guild_id: The ID of the guild.
        :param amount: Amount to transfer (must be > 0).
        :return: True if transferred successfully, False if invalid or insufficient funds.
        """
        if amount <= 0 or sender_id == receiver_id:
            return False

        async with self.session() as session:
            stmt_sender = select(EconomyWallet).where(
                EconomyWallet.user_id == sender_id,
                EconomyWallet.guild_id == guild_id,
            )
            sender_wallet = (await session.execute(stmt_sender)).scalar_one_or_none()
            if sender_wallet is None or sender_wallet.balance < amount:
                return False

            sender_wallet.balance -= amount

            stmt_receiver = select(EconomyWallet).where(
                EconomyWallet.user_id == receiver_id,
                EconomyWallet.guild_id == guild_id,
            )
            receiver_wallet = (await session.execute(stmt_receiver)).scalar_one_or_none()
            if receiver_wallet is None:
                receiver_wallet = EconomyWallet(user_id=receiver_id, guild_id=guild_id, balance=amount)
                session.add(receiver_wallet)
            else:
                receiver_wallet.balance += amount

            return True

    async def get_leaderboard(self, guild_id: int, limit: int = 10) -> Sequence[EconomyWallet]:
        """
        Get the top richest wallets in a guild ordered by balance descending.

        :param guild_id: The ID of the guild.
        :param limit: Maximum number of entries to return.
        :return: Sequence of EconomyWallet models with balance > 0.
        """
        async with self.session() as session:
            stmt = (
                select(EconomyWallet)
                .where(
                    EconomyWallet.guild_id == guild_id,
                    EconomyWallet.balance > 0,
                )
                .order_by(EconomyWallet.balance.desc())
                .limit(limit)
            )
            result = (await session.execute(stmt)).scalars().all()
            return result


class GamblingRepository(BaseRepository):
    """Repository for prediction bet pools and wagers."""

    async def _credit_wallet(self, session: AsyncSession, user_id: int, guild_id: int, amount: int) -> None:
        """Helper to credit a user's wallet within an active session."""
        if amount <= 0:
            return
        stmt = select(EconomyWallet).where(
            EconomyWallet.user_id == user_id,
            EconomyWallet.guild_id == guild_id,
        )
        wallet = (await session.execute(stmt)).scalar_one_or_none()
        if wallet is None:
            wallet = EconomyWallet(user_id=user_id, guild_id=guild_id, balance=amount)
            session.add(wallet)
        else:
            wallet.balance += amount

    async def _deduct_wallet_balance(self, session: AsyncSession, user_id: int, guild_id: int, amount: int) -> bool:
        """Deduct balance from user's wallet if sufficient."""
        stmt = select(EconomyWallet).where(
            EconomyWallet.user_id == user_id,
            EconomyWallet.guild_id == guild_id,
        )
        wallet = (await session.execute(stmt)).scalar_one_or_none()
        if wallet is None or wallet.balance < amount:
            return False
        wallet.balance -= amount
        return True

    def _apply_wager(
        self,
        session: AsyncSession,
        pool_id: int,
        user_id: int,
        guild_id: int,
        choice: str,
        amount: int,
        existing: BetWager | None,
    ) -> None:
        """Create a new wager or increment an existing wager."""
        if existing is not None:
            existing.amount += amount
        else:
            session.add(
                BetWager(
                    pool_id=pool_id,
                    user_id=user_id,
                    guild_id=guild_id,
                    choice=choice,
                    amount=amount,
                )
            )

    async def _refund_wagers(self, session: AsyncSession, guild_id: int, wagers: Sequence[BetWager]) -> None:
        """Refund all wagers to their respective users."""
        for wager in wagers:
            await self._credit_wallet(session, wager.user_id, guild_id, wager.amount)

    async def _distribute_payouts(
        self,
        session: AsyncSession,
        guild_id: int,
        winning_wagers: Sequence[BetWager],
        total_pool: int,
        winning_side_total: int,
    ) -> dict[int, int]:
        """Distribute proportional payouts to winning wagers."""
        payouts: dict[int, int] = {}
        for wager in winning_wagers:
            payout = (wager.amount * total_pool) // winning_side_total
            if payout > 0:
                await self._credit_wallet(session, wager.user_id, guild_id, payout)
                payouts[wager.user_id] = payouts.get(wager.user_id, 0) + payout
        return payouts

    def _is_pool_expired(self, pool: BetPool) -> bool:
        """Check if a bet pool's lock deadline has passed."""
        if pool.locks_at is None:
            return False
        now = datetime.now(timezone.utc)
        locks_at = pool.locks_at
        if locks_at.tzinfo is None:
            locks_at = locks_at.replace(tzinfo=timezone.utc)
        else:
            locks_at = locks_at.astimezone(timezone.utc)
        return now >= locks_at

    def _check_pool_accepts_options(self, pool: BetPool | None) -> str | None:
        """Check whether a pool can accept new options, returning an error message if not."""
        if pool is None or not pool.is_open:
            return "Bet pool not found or closed."
        if self._is_pool_expired(pool):
            pool.is_locked = True
            return "Betting is locked for this pool."
        if pool.is_locked:
            return "Betting is locked for this pool."
        if not pool.allow_custom_options:
            return "Custom options are not allowed for this pool."
        return None

    def _check_pool_accepts_wagers(self, pool: BetPool | None) -> bool:
        """Check whether a pool can accept new wagers."""
        if pool is None or not pool.is_open:
            return False
        if self._is_pool_expired(pool):
            pool.is_locked = True
            return False
        return not pool.is_locked

    def _can_user_wager_on_choice(self, existing: BetWager | None, choice: str) -> bool:
        """Return False if user already wagered on a different choice."""
        if existing is not None and existing.choice.casefold() != choice.casefold():
            return False
        return True

    async def create_bet_pool(
        self,
        guild_id: int,
        creator_id: int,
        title: str,
        options: Sequence[str] | None = None,
        allow_custom_options: bool = True,
        locks_at: datetime | None = None,
        channel_id: int | None = None,
        message_id: int | None = None,
        **kwargs: Any,
    ) -> BetPool:
        """Create a new open bet pool with optional initial options."""
        clean_title = title.strip()
        if options is None and "option_a" in kwargs and "option_b" in kwargs:
            options = [str(kwargs["option_a"]), str(kwargs["option_b"])]
        opt_list = [o.strip() for o in options] if options else []
        if not opt_list:
            allow_custom_options = True
        if locks_at is not None:
            locks_at = (
                locks_at.replace(tzinfo=timezone.utc) if locks_at.tzinfo is None else locks_at.astimezone(timezone.utc)
            )

        async with self.session() as session:
            pool = BetPool(
                guild_id=guild_id,
                channel_id=channel_id,
                message_id=message_id,
                creator_id=creator_id,
                title=clean_title,
                allow_custom_options=allow_custom_options,
                is_open=True,
                is_locked=False,
                locks_at=locks_at,
                winning_option=None,
            )
            session.add(pool)
            await session.flush()

            seen: set[str] = set()
            for label in opt_list[:MAX_BET_OPTIONS]:
                if label and label.casefold() not in seen:
                    seen.add(label.casefold())
                    session.add(
                        BetOption(
                            pool_id=pool.id,
                            label=label[:100],
                            creator_id=creator_id,
                        )
                    )
            await session.flush()
            return pool

    async def set_pool_message(self, pool_id: int, guild_id: int, channel_id: int, message_id: int) -> bool:
        """Save the Discord channel and message IDs for a bet pool."""
        async with self.session() as session:
            stmt = select(BetPool).where(
                BetPool.id == pool_id,
                BetPool.guild_id == guild_id,
            )
            pool = (await session.execute(stmt)).scalar_one_or_none()
            if pool is None:
                return False
            pool.channel_id = channel_id
            pool.message_id = message_id
            return True

    async def get_bet_pool(self, pool_id: int, guild_id: int) -> BetPool | None:
        """Get a bet pool by ID and guild ID."""
        async with self.session() as session:
            stmt = select(BetPool).where(
                BetPool.id == pool_id,
                BetPool.guild_id == guild_id,
            )
            return (await session.execute(stmt)).scalar_one_or_none()

    async def get_open_bet_pools(self, guild_id: int) -> Sequence[BetPool]:
        """Get all open bet pools in a guild ordered by ID descending."""
        async with self.session() as session:
            stmt = (
                select(BetPool)
                .where(
                    BetPool.guild_id == guild_id,
                    BetPool.is_open.is_(True),
                )
                .order_by(BetPool.id.desc())
            )
            return (await session.execute(stmt)).scalars().all()

    async def get_all_open_bet_pools(self) -> Sequence[BetPool]:
        """Get all open bet pools across all guilds ordered by ID descending."""
        async with self.session() as session:
            stmt = select(BetPool).where(BetPool.is_open.is_(True)).order_by(BetPool.id.desc())
            return (await session.execute(stmt)).scalars().all()

    async def get_pool_options(self, pool_id: int) -> Sequence[BetOption]:
        """Get all options for a bet pool ordered by ID ascending."""
        async with self.session() as session:
            stmt = select(BetOption).where(BetOption.pool_id == pool_id).order_by(BetOption.id.asc())
            return (await session.execute(stmt)).scalars().all()

    async def get_pool_wagers(self, pool_id: int, guild_id: int) -> Sequence[BetWager]:
        """Get all wagers for a pool."""
        async with self.session() as session:
            stmt = select(BetWager).where(
                BetWager.pool_id == pool_id,
                BetWager.guild_id == guild_id,
            )
            return (await session.execute(stmt)).scalars().all()

    async def add_bet_option(
        self, pool_id: int, guild_id: int, creator_id: int, label: str
    ) -> tuple[bool, BetOption | None, str]:
        """
        Add a custom option to an open, unlocked bet pool.

        Returns (success, option_model, message).
        If an option with the same label already exists, returns that option.
        """
        clean_label = label.strip()
        if not clean_label or len(clean_label) > 100:
            return False, None, "Option label must be between 1 and 100 characters."

        async with self.session() as session:
            stmt_pool = select(BetPool).where(
                BetPool.id == pool_id,
                BetPool.guild_id == guild_id,
            )
            pool = (await session.execute(stmt_pool)).scalar_one_or_none()
            err = self._check_pool_accepts_options(pool)
            if err:
                return False, None, err

            stmt_opts = select(BetOption).where(BetOption.pool_id == pool_id)
            existing_opts = (await session.execute(stmt_opts)).scalars().all()

            for opt in existing_opts:
                if opt.label.casefold() == clean_label.casefold():
                    return True, opt, "Option already exists."

            if len(existing_opts) >= MAX_BET_OPTIONS:
                return False, None, f"Maximum of {MAX_BET_OPTIONS} options reached."

            new_opt = BetOption(pool_id=pool_id, label=clean_label, creator_id=creator_id)
            session.add(new_opt)
            await session.flush()
            return True, new_opt, "Option added successfully."

    async def place_wager(self, pool_id: int, user_id: int, guild_id: int, choice: str, amount: int) -> bool:
        """
        Atomically place a wager on an open, unlocked bet pool.

        Validates amount > 0, option existence, and single-option-per-user constraint.
        """
        clean_choice = choice.strip()
        if amount <= 0 or not clean_choice:
            return False

        async with self.session() as session:
            stmt_pool = select(BetPool).where(
                BetPool.id == pool_id,
                BetPool.guild_id == guild_id,
            )
            pool = (await session.execute(stmt_pool)).scalar_one_or_none()
            if not self._check_pool_accepts_wagers(pool):
                return False

            stmt_opts = select(BetOption).where(BetOption.pool_id == pool_id)
            existing_opts = (await session.execute(stmt_opts)).scalars().all()
            matching_opt = next((o for o in existing_opts if o.label.casefold() == clean_choice.casefold()), None)
            if matching_opt is None:
                return False

            canonical_choice = matching_opt.label
            stmt_wager = select(BetWager).where(
                BetWager.pool_id == pool_id,
                BetWager.user_id == user_id,
            )
            existing = (await session.execute(stmt_wager)).scalar_one_or_none()
            if not self._can_user_wager_on_choice(existing, canonical_choice):
                return False

            if not await self._deduct_wallet_balance(session, user_id, guild_id, amount):
                return False

            self._apply_wager(session, pool_id, user_id, guild_id, canonical_choice, amount, existing)
            return True

    async def lock_bet_pool(self, pool_id: int, guild_id: int) -> bool:
        """Lock an open bet pool against further wagering."""
        async with self.session() as session:
            stmt_pool = select(BetPool).where(
                BetPool.id == pool_id,
                BetPool.guild_id == guild_id,
            )
            pool = (await session.execute(stmt_pool)).scalar_one_or_none()
            if pool is None or not pool.is_open or pool.is_locked:
                return False
            pool.is_locked = True
            return True

    async def auto_lock_expired_pools(self) -> Sequence[BetPool]:
        """Find and lock all open, unlocked pools whose locks_at timestamp has passed."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        async with self.session() as session:
            stmt = select(BetPool).where(
                BetPool.is_open.is_(True),
                BetPool.is_locked.is_(False),
                BetPool.locks_at.is_not(None),
                BetPool.locks_at <= now,
            )
            expired_pools = (await session.execute(stmt)).scalars().all()
            for pool in expired_pools:
                pool.is_locked = True
            return expired_pools

    async def resolve_bet_pool(self, pool_id: int, guild_id: int, winning_choice: str) -> dict[int, int] | None:
        """
        Atomically resolve a bet pool, paying out winners or refunding if no winners.

        :return: Mapping of user_id to payout amount, {} if refunded due to zero winners,
                 or None if pool not found or already closed.
        """
        clean_choice = winning_choice.strip()
        if not clean_choice:
            return None

        async with self.session() as session:
            stmt_pool = select(BetPool).where(
                BetPool.id == pool_id,
                BetPool.guild_id == guild_id,
            )
            pool = (await session.execute(stmt_pool)).scalar_one_or_none()
            if pool is None or not pool.is_open:
                return None

            pool.is_open = False
            pool.is_locked = True
            pool.winning_option = clean_choice

            stmt_wagers = select(BetWager).where(
                BetWager.pool_id == pool_id,
                BetWager.guild_id == guild_id,
            )
            wagers = (await session.execute(stmt_wagers)).scalars().all()

            winning_wagers = [w for w in wagers if w.choice.casefold() == clean_choice.casefold()]
            winning_side_total = sum(w.amount for w in winning_wagers)
            if winning_side_total == 0:
                await self._refund_wagers(session, guild_id, wagers)
                return {}

            total_pool = sum(w.amount for w in wagers)
            return await self._distribute_payouts(session, guild_id, winning_wagers, total_pool, winning_side_total)

    async def cancel_bet_pool(self, pool_id: int, guild_id: int) -> bool:
        """
        Atomically cancel an open bet pool and refund all wagers.

        :return: True if successfully cancelled, False if pool not found or already closed.
        """
        async with self.session() as session:
            stmt_pool = select(BetPool).where(
                BetPool.id == pool_id,
                BetPool.guild_id == guild_id,
            )
            pool = (await session.execute(stmt_pool)).scalar_one_or_none()
            if pool is None or not pool.is_open:
                return False

            pool.is_open = False
            pool.is_locked = True
            pool.winning_option = "CANCELLED"

            stmt_wagers = select(BetWager).where(
                BetWager.pool_id == pool_id,
                BetWager.guild_id == guild_id,
            )
            wagers = (await session.execute(stmt_wagers)).scalars().all()
            await self._refund_wagers(session, guild_id, wagers)
            return True
