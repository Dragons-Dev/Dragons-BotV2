from collections.abc import Sequence

from sqlalchemy import select

from utils.orm_database.repository import BaseRepository

from .models import EconomyWallet

__all__ = ["EconomyRepository"]


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
            stmt = select(EconomyWallet).where(
                EconomyWallet.user_id == user_id,
                EconomyWallet.guild_id == guild_id,
            )
            wallet = (await session.execute(stmt)).scalar_one_or_none()
            if wallet is None or wallet.balance < amount:
                return False

            wallet.balance -= amount
            return True

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
