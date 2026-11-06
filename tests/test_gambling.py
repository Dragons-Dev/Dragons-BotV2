from datetime import datetime
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from extensions.economy.gambling import Gambling, _calculate_slot_multiplier
from extensions.economy.models import BetPool, BetWager
from extensions.economy.repository import EconomyRepository, GamblingRepository
from utils.enums import SettingsEnum
from utils.orm_database import Base, ORMDataBase


class TestSlotMultiplier(unittest.TestCase):
    def test_three_dragons_returns_ten(self):
        self.assertEqual(_calculate_slot_multiplier(["🐉", "🐉", "🐉"]), 10)

    def test_three_other_symbols_returns_five(self):
        self.assertEqual(_calculate_slot_multiplier(["🍒", "🍒", "🍒"]), 5)
        self.assertEqual(_calculate_slot_multiplier(["💎", "💎", "💎"]), 5)

    def test_two_of_a_kind_returns_two(self):
        self.assertEqual(_calculate_slot_multiplier(["🍒", "🍒", "🍋"]), 2)
        self.assertEqual(_calculate_slot_multiplier(["🔔", "💎", "💎"]), 2)
        self.assertEqual(_calculate_slot_multiplier(["🐉", "🍋", "🐉"]), 2)

    def test_no_match_returns_zero(self):
        self.assertEqual(_calculate_slot_multiplier(["🍒", "🍋", "💎"]), 0)


class TestGamblingRepository(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.session_maker: async_sessionmaker[AsyncSession] = async_sessionmaker(self.engine, expire_on_commit=False)
        ORMDataBase._discover_models(SimpleNamespace(logger=None))  # type: ignore[arg-type]
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.economy_repo = EconomyRepository(self.session_maker)
        self.repo = GamblingRepository(self.session_maker)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_create_and_get_bet_pool(self):
        pool = await self.repo.create_bet_pool(
            guild_id=10,
            creator_id=100,
            title="Will it rain tomorrow?",
            option_a="Yes",
            option_b="No",
        )
        self.assertIsNotNone(pool.id)
        self.assertEqual(pool.guild_id, 10)
        self.assertEqual(pool.creator_id, 100)
        self.assertEqual(pool.title, "Will it rain tomorrow?")
        self.assertEqual(pool.option_a, "Yes")
        self.assertEqual(pool.option_b, "No")
        self.assertTrue(pool.is_open)
        self.assertIsNone(pool.winning_option)

        fetched = await self.repo.get_bet_pool(pool.id, guild_id=10)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.id, pool.id)  # type: ignore[union-attr]

        # Wrong guild returns None
        wrong_guild = await self.repo.get_bet_pool(pool.id, guild_id=999)
        self.assertIsNone(wrong_guild)

    async def test_get_open_bet_pools(self):
        p1 = await self.repo.create_bet_pool(10, 100, "Bet 1", "A", "B")
        p2 = await self.repo.create_bet_pool(10, 100, "Bet 2", "A", "B")
        await self.repo.create_bet_pool(20, 100, "Bet Other Guild", "A", "B")

        open_pools = await self.repo.get_open_bet_pools(10)
        self.assertEqual(len(open_pools), 2)
        pool_ids = [p.id for p in open_pools]
        self.assertIn(p1.id, pool_ids)
        self.assertIn(p2.id, pool_ids)

        # Cancel one, verify not in open pools
        await self.repo.cancel_bet_pool(p1.id, 10)
        open_after = await self.repo.get_open_bet_pools(10)
        self.assertEqual(len(open_after), 1)
        self.assertEqual(open_after[0].id, p2.id)

    async def test_place_wager_validation(self):
        pool = await self.repo.create_bet_pool(10, 100, "Bet", "A", "B")
        await self.economy_repo.set_balance(user_id=1, guild_id=10, amount=500)

        # Invalid amount
        self.assertFalse(await self.repo.place_wager(pool.id, 1, 10, "A", 0))
        self.assertFalse(await self.repo.place_wager(pool.id, 1, 10, "A", -50))

        # Invalid choice
        self.assertFalse(await self.repo.place_wager(pool.id, 1, 10, "C", 50))

        # Non-existent pool
        self.assertFalse(await self.repo.place_wager(9999, 1, 10, "A", 50))

    async def test_place_wager_insufficient_balance(self):
        pool = await self.repo.create_bet_pool(10, 100, "Bet", "A", "B")
        await self.economy_repo.set_balance(user_id=1, guild_id=10, amount=50)

        # Try to wager more than balance
        success = await self.repo.place_wager(pool.id, 1, 10, "A", 100)
        self.assertFalse(success)
        self.assertEqual(await self.economy_repo.get_balance(1, 10), 50)
        wagers = await self.repo.get_pool_wagers(pool.id, 10)
        self.assertEqual(len(wagers), 0)

    async def test_place_wager_success_and_increment(self):
        pool = await self.repo.create_bet_pool(10, 100, "Bet", "A", "B")
        await self.economy_repo.set_balance(user_id=1, guild_id=10, amount=500)

        # First wager of 100 on A
        success1 = await self.repo.place_wager(pool.id, 1, 10, "A", 100)
        self.assertTrue(success1)
        self.assertEqual(await self.economy_repo.get_balance(1, 10), 400)

        wagers = await self.repo.get_pool_wagers(pool.id, 10)
        self.assertEqual(len(wagers), 1)
        self.assertEqual(wagers[0].amount, 100)
        self.assertEqual(wagers[0].choice, "A")

        # Second wager of 50 on same choice A increments wager
        success2 = await self.repo.place_wager(pool.id, 1, 10, "A", 50)
        self.assertTrue(success2)
        self.assertEqual(await self.economy_repo.get_balance(1, 10), 350)

        wagers_after = await self.repo.get_pool_wagers(pool.id, 10)
        self.assertEqual(len(wagers_after), 1)
        self.assertEqual(wagers_after[0].amount, 150)

    async def test_place_wager_opposite_side_rejection(self):
        pool = await self.repo.create_bet_pool(10, 100, "Bet", "A", "B")
        await self.economy_repo.set_balance(user_id=1, guild_id=10, amount=500)

        # First wager on A
        self.assertTrue(await self.repo.place_wager(pool.id, 1, 10, "A", 100))

        # Attempt wager on B should be rejected
        self.assertFalse(await self.repo.place_wager(pool.id, 1, 10, "B", 50))
        # Balance should still be 400
        self.assertEqual(await self.economy_repo.get_balance(1, 10), 400)

    async def test_place_wager_closed_pool_rejection(self):
        pool = await self.repo.create_bet_pool(10, 100, "Bet", "A", "B")
        await self.economy_repo.set_balance(user_id=1, guild_id=10, amount=500)
        await self.repo.cancel_bet_pool(pool.id, 10)

        self.assertFalse(await self.repo.place_wager(pool.id, 1, 10, "A", 100))
        self.assertEqual(await self.economy_repo.get_balance(1, 10), 500)

    async def test_resolve_bet_pool_proportional_payout(self):
        pool = await self.repo.create_bet_pool(10, 100, "Bet", "Option A", "Option B")
        # User 1 bets 100 on A
        # User 2 bets 100 on A
        # User 3 bets 200 on B
        # Total pool = 400, Winning side (A) = 200
        # User 1 payout = 100 * 400 / 200 = 200
        # User 2 payout = 100 * 400 / 200 = 200
        await self.economy_repo.set_balance(1, 10, 100)
        await self.economy_repo.set_balance(2, 10, 100)
        await self.economy_repo.set_balance(3, 10, 200)

        await self.repo.place_wager(pool.id, 1, 10, "A", 100)
        await self.repo.place_wager(pool.id, 2, 10, "A", 100)
        await self.repo.place_wager(pool.id, 3, 10, "B", 200)

        # Before resolution, all balances are 0
        self.assertEqual(await self.economy_repo.get_balance(1, 10), 0)
        self.assertEqual(await self.economy_repo.get_balance(2, 10), 0)
        self.assertEqual(await self.economy_repo.get_balance(3, 10), 0)

        payouts = await self.repo.resolve_bet_pool(pool.id, 10, "A")
        self.assertIsNotNone(payouts)
        self.assertEqual(payouts, {1: 200, 2: 200})

        self.assertEqual(await self.economy_repo.get_balance(1, 10), 200)
        self.assertEqual(await self.economy_repo.get_balance(2, 10), 200)
        self.assertEqual(await self.economy_repo.get_balance(3, 10), 0)

        updated_pool = await self.repo.get_bet_pool(pool.id, 10)
        self.assertFalse(updated_pool.is_open)  # type: ignore[union-attr]
        self.assertEqual(updated_pool.winning_option, "A")  # type: ignore[union-attr]

        # Cannot resolve again
        self.assertIsNone(await self.repo.resolve_bet_pool(pool.id, 10, "A"))

    async def test_resolve_bet_pool_zero_winners_refunds(self):
        pool = await self.repo.create_bet_pool(10, 100, "Bet", "Option A", "Option B")
        # User 1 bets 100 on A
        # Nobody bets on B
        # B is chosen as winner -> zero winners, should refund User 1
        await self.economy_repo.set_balance(1, 10, 100)
        await self.repo.place_wager(pool.id, 1, 10, "A", 100)

        payouts = await self.repo.resolve_bet_pool(pool.id, 10, "B")
        self.assertEqual(payouts, {})
        # User 1 should have their 100 scales refunded
        self.assertEqual(await self.economy_repo.get_balance(1, 10), 100)

        updated_pool = await self.repo.get_bet_pool(pool.id, 10)
        self.assertFalse(updated_pool.is_open)  # type: ignore[union-attr]
        self.assertEqual(updated_pool.winning_option, "B")  # type: ignore[union-attr]

    async def test_resolve_bet_pool_invalid_choice(self):
        pool = await self.repo.create_bet_pool(10, 100, "Bet", "A", "B")
        self.assertIsNone(await self.repo.resolve_bet_pool(pool.id, 10, "X"))

    async def test_cancel_bet_pool_refunds_all(self):
        pool = await self.repo.create_bet_pool(10, 100, "Bet", "Option A", "Option B")
        await self.economy_repo.set_balance(1, 10, 100)
        await self.economy_repo.set_balance(2, 10, 200)

        await self.repo.place_wager(pool.id, 1, 10, "A", 100)
        await self.repo.place_wager(pool.id, 2, 10, "B", 200)

        success = await self.repo.cancel_bet_pool(pool.id, 10)
        self.assertTrue(success)

        # Both users refunded
        self.assertEqual(await self.economy_repo.get_balance(1, 10), 100)
        self.assertEqual(await self.economy_repo.get_balance(2, 10), 200)

        updated_pool = await self.repo.get_bet_pool(pool.id, 10)
        self.assertFalse(updated_pool.is_open)  # type: ignore[union-attr]
        self.assertEqual(updated_pool.winning_option, "CANCELLED")  # type: ignore[union-attr]

        # Cancel already closed pool returns False
        self.assertFalse(await self.repo.cancel_bet_pool(pool.id, 10))


class TestGamblingCogMiniGames(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.logger_patcher = patch("extensions.economy.gambling.CustomLogger")
        self.logger_patcher.start()
        self.mock_client = MagicMock()
        self.mock_client.boot_time = datetime.now()
        self.mock_economy_repo = MagicMock(spec=EconomyRepository)
        self.mock_gambling_repo = MagicMock(spec=GamblingRepository)
        self.cog = Gambling(
            self.mock_client,
            gambling_repo=self.mock_gambling_repo,
            economy_repo=self.mock_economy_repo,
        )
        for cmd in [self.cog.coinflip, self.cog.dice, self.cog.slots]:
            cmd.cog = self.cog

    def tearDown(self):
        self.logger_patcher.stop()

    def _make_ctx(self, user_id: int = 1, guild_id: int = 10):
        ctx = MagicMock()
        ctx.author = MagicMock(id=user_id, mention=f"<@{user_id}>")
        ctx.guild = MagicMock(id=guild_id, emojis=[])
        ctx.response.send_message = AsyncMock()
        return ctx

    async def test_coinflip_invalid_amount(self):
        ctx = self._make_ctx()
        await self.cog.coinflip(ctx, choice="heads", amount=0)
        ctx.response.send_message.assert_called_once()
        self.assertIn("must be greater than 0", ctx.response.send_message.call_args[0][0])
        self.assertTrue(ctx.response.send_message.call_args[1].get("ephemeral"))

    async def test_coinflip_insufficient_balance(self):
        ctx = self._make_ctx()
        self.mock_economy_repo.remove_balance = AsyncMock(return_value=False)
        self.mock_economy_repo.get_balance = AsyncMock(return_value=25)

        await self.cog.coinflip(ctx, choice="heads", amount=50)
        ctx.response.send_message.assert_called_once()
        self.assertIn("do not have enough", ctx.response.send_message.call_args[0][0])
        self.assertTrue(ctx.response.send_message.call_args[1].get("ephemeral"))

    async def test_coinflip_win(self):
        ctx = self._make_ctx()
        self.mock_economy_repo.remove_balance = AsyncMock(return_value=True)
        self.mock_economy_repo.add_balance = AsyncMock(return_value=200)
        self.mock_economy_repo.get_balance = AsyncMock(return_value=200)

        with patch("random.choice", return_value="heads"):
            await self.cog.coinflip(ctx, choice="heads", amount=100)

        self.mock_economy_repo.add_balance.assert_called_once_with(ctx.author.id, ctx.guild.id, 200)
        ctx.response.send_message.assert_called_once()
        embed = ctx.response.send_message.call_args[1]["embed"]
        self.assertIn("Winner", embed.title)

    async def test_coinflip_loss(self):
        ctx = self._make_ctx()
        self.mock_economy_repo.remove_balance = AsyncMock(return_value=True)
        self.mock_economy_repo.get_balance = AsyncMock(return_value=0)

        with patch("random.choice", return_value="tails"):
            await self.cog.coinflip(ctx, choice="heads", amount=100)

        self.mock_economy_repo.add_balance.assert_not_called()
        ctx.response.send_message.assert_called_once()
        embed = ctx.response.send_message.call_args[1]["embed"]
        self.assertIn("Lost", embed.title)

    async def test_dice_invalid_guess(self):
        ctx = self._make_ctx()
        await self.cog.dice(ctx, guess=7, amount=100)
        ctx.response.send_message.assert_called_once()
        self.assertIn("between 1 and 6", ctx.response.send_message.call_args[0][0])

    async def test_dice_win(self):
        ctx = self._make_ctx()
        self.mock_economy_repo.remove_balance = AsyncMock(return_value=True)
        self.mock_economy_repo.add_balance = AsyncMock(return_value=600)
        self.mock_economy_repo.get_balance = AsyncMock(return_value=600)

        with patch("random.randint", return_value=4):
            await self.cog.dice(ctx, guess=4, amount=100)

        self.mock_economy_repo.add_balance.assert_called_once_with(ctx.author.id, ctx.guild.id, 600)
        embed = ctx.response.send_message.call_args[1]["embed"]
        self.assertIn("Winner", embed.title)

    async def test_dice_loss(self):
        ctx = self._make_ctx()
        self.mock_economy_repo.remove_balance = AsyncMock(return_value=True)
        self.mock_economy_repo.get_balance = AsyncMock(return_value=0)

        with patch("random.randint", return_value=2):
            await self.cog.dice(ctx, guess=4, amount=100)

        self.mock_economy_repo.add_balance.assert_not_called()
        embed = ctx.response.send_message.call_args[1]["embed"]
        self.assertIn("Lost", embed.title)

    async def test_slots_three_dragons(self):
        ctx = self._make_ctx()
        self.mock_economy_repo.remove_balance = AsyncMock(return_value=True)
        self.mock_economy_repo.add_balance = AsyncMock(return_value=1000)
        self.mock_economy_repo.get_balance = AsyncMock(return_value=1000)

        with patch("random.choices", return_value=["🐉", "🐉", "🐉"]):
            await self.cog.slots(ctx, amount=100)

        self.mock_economy_repo.add_balance.assert_called_once_with(ctx.author.id, ctx.guild.id, 1000)
        embed = ctx.response.send_message.call_args[1]["embed"]
        self.assertIn("10x", embed.description)

    async def test_slots_three_matching(self):
        ctx = self._make_ctx()
        self.mock_economy_repo.remove_balance = AsyncMock(return_value=True)
        self.mock_economy_repo.add_balance = AsyncMock(return_value=500)
        self.mock_economy_repo.get_balance = AsyncMock(return_value=500)

        with patch("random.choices", return_value=["🍒", "🍒", "🍒"]):
            await self.cog.slots(ctx, amount=100)

        self.mock_economy_repo.add_balance.assert_called_once_with(ctx.author.id, ctx.guild.id, 500)
        embed = ctx.response.send_message.call_args[1]["embed"]
        self.assertIn("5x", embed.description)

    async def test_slots_two_matching(self):
        ctx = self._make_ctx()
        self.mock_economy_repo.remove_balance = AsyncMock(return_value=True)
        self.mock_economy_repo.add_balance = AsyncMock(return_value=200)
        self.mock_economy_repo.get_balance = AsyncMock(return_value=200)

        with patch("random.choices", return_value=["💎", "💎", "🍋"]):
            await self.cog.slots(ctx, amount=100)

        self.mock_economy_repo.add_balance.assert_called_once_with(ctx.author.id, ctx.guild.id, 200)
        embed = ctx.response.send_message.call_args[1]["embed"]
        self.assertIn("2x", embed.description)

    async def test_slots_no_matching(self):
        ctx = self._make_ctx()
        self.mock_economy_repo.remove_balance = AsyncMock(return_value=True)
        self.mock_economy_repo.get_balance = AsyncMock(return_value=0)

        with patch("random.choices", return_value=["🍒", "🍋", "🔔"]):
            await self.cog.slots(ctx, amount=100)

        self.mock_economy_repo.add_balance.assert_not_called()
        embed = ctx.response.send_message.call_args[1]["embed"]
        self.assertIn("Lost", embed.title)


class TestGamblingCogPredictionPools(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.logger_patcher = patch("extensions.economy.gambling.CustomLogger")
        self.logger_patcher.start()
        self.mock_client = MagicMock()
        self.mock_client.boot_time = datetime.now()
        self.mock_client.db = MagicMock()
        self.mock_economy_repo = MagicMock(spec=EconomyRepository)
        self.mock_gambling_repo = MagicMock(spec=GamblingRepository)
        self.cog = Gambling(
            self.mock_client,
            gambling_repo=self.mock_gambling_repo,
            economy_repo=self.mock_economy_repo,
        )
        for cmd in [
            self.cog.bet_create,
            self.cog.bet_place,
            self.cog.bet_list,
            self.cog.bet_resolve,
        ]:
            cmd.cog = self.cog

    def tearDown(self):
        self.logger_patcher.stop()

    def _make_ctx(self, user_id: int = 1, guild_id: int = 10, is_admin: bool = False, roles=None):
        ctx = MagicMock()
        ctx.author = MagicMock(id=user_id, mention=f"<@{user_id}>", roles=roles or [])
        ctx.author.guild_permissions = MagicMock(administrator=is_admin)
        ctx.guild = MagicMock(id=guild_id, emojis=[])
        ctx.response.send_message = AsyncMock()
        return ctx

    async def test_bet_create_empty_title_or_options(self):
        ctx = self._make_ctx()
        await self.cog.bet_create(ctx, title="   ", option_a="Yes", option_b="No")
        ctx.response.send_message.assert_called_once()
        self.assertIn("cannot be empty", ctx.response.send_message.call_args[0][0])

    async def test_bet_create_success(self):
        ctx = self._make_ctx(user_id=100, guild_id=10)
        created_pool = BetPool(
            id=1,
            guild_id=10,
            creator_id=100,
            title="Rain prediction",
            option_a="Yes",
            option_b="No",
            is_open=True,
            winning_option=None,
        )
        self.mock_gambling_repo.create_bet_pool = AsyncMock(return_value=created_pool)

        await self.cog.bet_create(ctx, title="Rain prediction", option_a="Yes", option_b="No")
        self.mock_gambling_repo.create_bet_pool.assert_called_once_with(10, 100, "Rain prediction", "Yes", "No")
        ctx.response.send_message.assert_called_once()
        embed = ctx.response.send_message.call_args[1]["embed"]
        self.assertIn("Bet Pool #1", embed.title)

    async def test_bet_place_pool_not_found(self):
        ctx = self._make_ctx()
        self.mock_gambling_repo.get_bet_pool = AsyncMock(return_value=None)

        await self.cog.bet_place(ctx, bet_id=999, choice="A", amount=50)
        self.assertIn("does not exist", ctx.response.send_message.call_args[0][0])

    async def test_bet_place_pool_closed(self):
        ctx = self._make_ctx()
        closed_pool = BetPool(id=1, guild_id=10, creator_id=100, title="T", option_a="A", option_b="B", is_open=False)
        self.mock_gambling_repo.get_bet_pool = AsyncMock(return_value=closed_pool)

        await self.cog.bet_place(ctx, bet_id=1, choice="A", amount=50)
        self.assertIn("already closed", ctx.response.send_message.call_args[0][0])

    async def test_bet_place_insufficient_balance(self):
        ctx = self._make_ctx()
        pool = BetPool(id=1, guild_id=10, creator_id=100, title="T", option_a="A", option_b="B", is_open=True)
        self.mock_gambling_repo.get_bet_pool = AsyncMock(return_value=pool)
        self.mock_gambling_repo.place_wager = AsyncMock(return_value=False)
        self.mock_gambling_repo.get_pool_wagers = AsyncMock(return_value=[])
        self.mock_economy_repo.get_balance = AsyncMock(return_value=10)

        await self.cog.bet_place(ctx, bet_id=1, choice="A", amount=50)
        self.assertIn("do not have enough", ctx.response.send_message.call_args[0][0])

    async def test_bet_place_opposite_choice_conflict(self):
        ctx = self._make_ctx(user_id=1)
        pool = BetPool(id=1, guild_id=10, creator_id=100, title="T", option_a="A", option_b="B", is_open=True)
        self.mock_gambling_repo.get_bet_pool = AsyncMock(return_value=pool)
        self.mock_gambling_repo.place_wager = AsyncMock(return_value=False)
        existing_wager = BetWager(id=1, pool_id=1, user_id=1, guild_id=10, choice="A", amount=50)
        self.mock_gambling_repo.get_pool_wagers = AsyncMock(return_value=[existing_wager])

        await self.cog.bet_place(ctx, bet_id=1, choice="B", amount=50)
        self.assertIn("already wagered on the other option", ctx.response.send_message.call_args[0][0])

    async def test_bet_place_success(self):
        ctx = self._make_ctx()
        pool = BetPool(
            id=1,
            guild_id=10,
            creator_id=100,
            title="T",
            option_a="Red",
            option_b="Blue",
            is_open=True,
        )
        self.mock_gambling_repo.get_bet_pool = AsyncMock(return_value=pool)
        self.mock_gambling_repo.place_wager = AsyncMock(return_value=True)

        await self.cog.bet_place(ctx, bet_id=1, choice="A", amount=50)
        self.mock_gambling_repo.place_wager.assert_called_once_with(1, ctx.author.id, 10, "A", 50)
        embed = ctx.response.send_message.call_args[1]["embed"]
        self.assertIn("Wager Placed!", embed.title)

    async def test_bet_list_empty(self):
        ctx = self._make_ctx()
        self.mock_gambling_repo.get_open_bet_pools = AsyncMock(return_value=[])

        await self.cog.bet_list(ctx)
        self.assertIn("no open bet pools", ctx.response.send_message.call_args[0][0])

    async def test_bet_list_with_pools(self):
        ctx = self._make_ctx()
        pool = BetPool(
            id=1,
            guild_id=10,
            creator_id=100,
            title="Match 1",
            option_a="Team A",
            option_b="Team B",
            is_open=True,
        )
        self.mock_gambling_repo.get_open_bet_pools = AsyncMock(return_value=[pool])
        wager = BetWager(id=1, pool_id=1, user_id=2, guild_id=10, choice="A", amount=150)
        self.mock_gambling_repo.get_pool_wagers = AsyncMock(return_value=[wager])

        await self.cog.bet_list(ctx)
        embed = ctx.response.send_message.call_args[1]["embed"]
        self.assertEqual(embed.title, "Active Prediction Bet Pools")
        self.assertEqual(len(embed.fields), 1)

    async def test_bet_resolve_unauthorized_user(self):
        ctx = self._make_ctx(user_id=999, is_admin=False, roles=[])
        pool = BetPool(id=1, guild_id=10, creator_id=100, title="T", option_a="A", option_b="B", is_open=True)
        self.mock_gambling_repo.get_bet_pool = AsyncMock(return_value=pool)
        self.mock_client.db.get_setting = AsyncMock(return_value=None)

        await self.cog.bet_resolve(ctx, bet_id=1, outcome="A")
        self.assertIn("Only the bet creator or a team member", ctx.response.send_message.call_args[0][0])
        self.assertTrue(ctx.response.send_message.call_args[1].get("ephemeral"))
        self.mock_gambling_repo.resolve_bet_pool.assert_not_called()

    async def test_bet_resolve_authorized_by_creator(self):
        # User is the creator
        ctx = self._make_ctx(user_id=100, is_admin=False)
        pool = BetPool(id=1, guild_id=10, creator_id=100, title="T", option_a="A", option_b="B", is_open=True)
        self.mock_gambling_repo.get_bet_pool = AsyncMock(return_value=pool)
        self.mock_gambling_repo.resolve_bet_pool = AsyncMock(return_value={2: 400})

        await self.cog.bet_resolve(ctx, bet_id=1, outcome="A")
        self.mock_gambling_repo.resolve_bet_pool.assert_called_once_with(1, 10, "A")
        embed = ctx.response.send_message.call_args[1]["embed"]
        self.assertIn("Resolved", embed.title)

    async def test_bet_resolve_authorized_by_admin(self):
        # User is not creator, but is admin
        ctx = self._make_ctx(user_id=200, is_admin=True)
        pool = BetPool(id=1, guild_id=10, creator_id=100, title="T", option_a="A", option_b="B", is_open=True)
        self.mock_gambling_repo.get_bet_pool = AsyncMock(return_value=pool)
        self.mock_gambling_repo.resolve_bet_pool = AsyncMock(return_value={2: 400})

        await self.cog.bet_resolve(ctx, bet_id=1, outcome="A")
        self.mock_gambling_repo.resolve_bet_pool.assert_called_once_with(1, 10, "A")
        embed = ctx.response.send_message.call_args[1]["embed"]
        self.assertIn("Resolved", embed.title)

    async def test_bet_resolve_authorized_by_team_role(self):
        # User is not creator, not admin, but has TeamRole
        role = SimpleNamespace(id=555)
        ctx = self._make_ctx(user_id=300, is_admin=False, roles=[role])
        pool = BetPool(id=1, guild_id=10, creator_id=100, title="T", option_a="A", option_b="B", is_open=True)
        self.mock_gambling_repo.get_bet_pool = AsyncMock(return_value=pool)
        self.mock_client.db.get_setting = AsyncMock(
            return_value=SimpleNamespace(setting=SettingsEnum.TeamRole.value, value=555)
        )
        self.mock_gambling_repo.resolve_bet_pool = AsyncMock(return_value={2: 400})

        await self.cog.bet_resolve(ctx, bet_id=1, outcome="B")
        self.mock_gambling_repo.resolve_bet_pool.assert_called_once_with(1, 10, "B")
        embed = ctx.response.send_message.call_args[1]["embed"]
        self.assertIn("Resolved", embed.title)

    async def test_bet_resolve_cancel(self):
        ctx = self._make_ctx(user_id=100)
        pool = BetPool(id=1, guild_id=10, creator_id=100, title="T", option_a="A", option_b="B", is_open=True)
        self.mock_gambling_repo.get_bet_pool = AsyncMock(return_value=pool)
        self.mock_gambling_repo.cancel_bet_pool = AsyncMock(return_value=True)

        await self.cog.bet_resolve(ctx, bet_id=1, outcome="cancel")
        self.mock_gambling_repo.cancel_bet_pool.assert_called_once_with(1, 10)
        embed = ctx.response.send_message.call_args[1]["embed"]
        self.assertIn("Cancelled", embed.title)

    async def test_bet_resolve_zero_winners_announcement(self):
        ctx = self._make_ctx(user_id=100)
        pool = BetPool(id=1, guild_id=10, creator_id=100, title="T", option_a="A", option_b="B", is_open=True)
        self.mock_gambling_repo.get_bet_pool = AsyncMock(return_value=pool)
        self.mock_gambling_repo.resolve_bet_pool = AsyncMock(return_value={})

        await self.cog.bet_resolve(ctx, bet_id=1, outcome="A")
        embed = ctx.response.send_message.call_args[1]["embed"]
        self.assertIn("refunded", embed.description.lower())
