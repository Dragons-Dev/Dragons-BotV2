from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from extensions.economy.gambling import (
    AddCustomOptionModal,
    BetCreateModal,
    BetPoolView,
    BetSetupView,
    CancelButton,
    CustomOutcomeModal,
    Gambling,
    LockButton,
    PlaceWagerModal,
    ResolveBetView,
    ResolveButton,
    _calculate_slot_multiplier,
    _parse_bet_duration,
    _parse_bet_options,
)
from extensions.economy.models import MAX_BET_OPTIONS, BetOption, BetPool, BetWager
from extensions.economy.repository import EconomyRepository, GamblingRepository
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


class TestBetParsers(unittest.TestCase):
    def test_parse_bet_duration_valid(self):
        self.assertEqual(_parse_bet_duration("30s"), timedelta(seconds=30))
        self.assertEqual(_parse_bet_duration("15m"), timedelta(minutes=15))
        self.assertEqual(_parse_bet_duration("2h"), timedelta(hours=2))
        self.assertEqual(_parse_bet_duration("1d"), timedelta(days=1))
        self.assertEqual(_parse_bet_duration("2w"), timedelta(weeks=2))
        self.assertEqual(_parse_bet_duration("1h 30m"), timedelta(hours=1, minutes=30))

    def test_parse_bet_duration_invalid(self):
        self.assertIsNone(_parse_bet_duration(""))
        self.assertIsNone(_parse_bet_duration("   "))
        self.assertIsNone(_parse_bet_duration("invalid"))
        self.assertIsNone(_parse_bet_duration("30x"))
        self.assertIsNone(_parse_bet_duration("-5m"))
        self.assertIsNone(_parse_bet_duration("0m"))

    def test_parse_bet_options_normal(self):
        text = "Option A\nOption B\nOption C"
        opts = _parse_bet_options(text)
        self.assertEqual(opts, ["Option A", "Option B", "Option C"])

    def test_parse_bet_options_stripping_and_empty_lines(self):
        text = "   Red Dragon   \n\n\n   Blue Dragon  \n"
        opts = _parse_bet_options(text)
        self.assertEqual(opts, ["Red Dragon", "Blue Dragon"])

    def test_parse_bet_options_deduplication(self):
        text = "Yes\nNo\nyes\nNO\nMaybe"
        opts = _parse_bet_options(text)
        self.assertEqual(opts, ["Yes", "No", "Maybe"])

    def test_parse_bet_options_max_25(self):
        text = "\n".join(f"Opt {i}" for i in range(30))
        opts = _parse_bet_options(text)
        self.assertEqual(len(opts), MAX_BET_OPTIONS)
        self.assertEqual(opts[0], "Opt 0")
        self.assertEqual(opts[-1], "Opt 24")

    def test_parse_bet_options_exceeds_100_chars_raises(self):
        long_line = "A" * 101
        with self.assertRaises(ValueError) as ctx:
            _parse_bet_options(long_line)
        self.assertIn("exceeds maximum length of 100", str(ctx.exception))


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

    async def test_create_and_get_bet_pool_with_options(self):
        pool = await self.repo.create_bet_pool(
            guild_id=10,
            creator_id=100,
            title="Will it rain tomorrow?",
            options=["Yes", "No"],
            allow_custom_options=True,
        )
        self.assertIsNotNone(pool.id)
        self.assertEqual(pool.guild_id, 10)
        self.assertEqual(pool.creator_id, 100)
        self.assertEqual(pool.title, "Will it rain tomorrow?")
        self.assertTrue(pool.allow_custom_options)
        self.assertTrue(pool.is_open)
        self.assertFalse(pool.is_locked)
        self.assertIsNone(pool.winning_option)

        options = await self.repo.get_pool_options(pool.id)
        self.assertEqual(len(options), 2)
        self.assertEqual([o.label for o in options], ["Yes", "No"])

        fetched = await self.repo.get_bet_pool(pool.id, guild_id=10)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.id, pool.id)  # type: ignore[union-attr]

        # Wrong guild returns None
        wrong_guild = await self.repo.get_bet_pool(pool.id, guild_id=999)
        self.assertIsNone(wrong_guild)

    async def test_create_bet_pool_zero_options_forces_custom_options(self):
        pool = await self.repo.create_bet_pool(
            guild_id=10,
            creator_id=100,
            title="Open ended question",
            options=[],
            allow_custom_options=False,
        )
        self.assertTrue(pool.allow_custom_options)
        options = await self.repo.get_pool_options(pool.id)
        self.assertEqual(len(options), 0)

    async def test_set_pool_message(self):
        pool = await self.repo.create_bet_pool(10, 100, "Bet", options=["A"])
        success = await self.repo.set_pool_message(pool.id, 10, channel_id=222, message_id=333)
        self.assertTrue(success)

        fetched = await self.repo.get_bet_pool(pool.id, 10)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.channel_id, 222)  # type: ignore[union-attr]
        self.assertEqual(fetched.message_id, 333)  # type: ignore[union-attr]

        # Non-existent pool returns False
        self.assertFalse(await self.repo.set_pool_message(999, 10, 222, 333))

    async def test_get_open_bet_pools(self):
        p1 = await self.repo.create_bet_pool(10, 100, "Bet 1", options=["A", "B"])
        p2 = await self.repo.create_bet_pool(10, 100, "Bet 2", options=["A", "B"])
        await self.repo.create_bet_pool(20, 100, "Bet Other Guild", options=["A", "B"])

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

    async def test_add_bet_option_success_and_duplicate(self):
        pool = await self.repo.create_bet_pool(10, 100, "Bet", options=["Option 1"])
        success, opt, msg = await self.repo.add_bet_option(pool.id, 10, 100, "Option 2")
        self.assertTrue(success)
        self.assertIsNotNone(opt)
        self.assertEqual(opt.label, "Option 2")  # type: ignore[union-attr]

        # Case-insensitive duplicate returns existing option
        success2, opt2, msg2 = await self.repo.add_bet_option(pool.id, 10, 101, "option 2")
        self.assertTrue(success2)
        self.assertIsNotNone(opt2)
        self.assertEqual(opt2.id, opt.id)  # type: ignore[union-attr]
        self.assertEqual(msg2, "Option already exists.")

    async def test_add_bet_option_disallowed_when_custom_false(self):
        pool = await self.repo.create_bet_pool(10, 100, "Bet", options=["A", "B"], allow_custom_options=False)
        success, opt, msg = await self.repo.add_bet_option(pool.id, 10, 100, "Option C")
        self.assertFalse(success)
        self.assertIsNone(opt)
        self.assertIn("not allowed", msg)

    async def test_add_bet_option_max_25_options(self):
        initial = [f"Opt {i}" for i in range(MAX_BET_OPTIONS)]
        pool = await self.repo.create_bet_pool(10, 100, "Bet", options=initial, allow_custom_options=True)
        success, opt, msg = await self.repo.add_bet_option(pool.id, 10, 100, "Overflow Opt")
        self.assertFalse(success)
        self.assertIsNone(opt)
        self.assertIn("Maximum of 25 options reached", msg)

    async def test_add_bet_option_locked_or_expired(self):
        # Locked pool
        pool = await self.repo.create_bet_pool(10, 100, "Bet", options=["A"])
        await self.repo.lock_bet_pool(pool.id, 10)
        success, _, msg = await self.repo.add_bet_option(pool.id, 10, 100, "B")
        self.assertFalse(success)
        self.assertIn("locked", msg)

        # Expired pool
        past_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        pool_exp = await self.repo.create_bet_pool(10, 100, "Bet Exp", options=["A"], locks_at=past_time)
        success_exp, _, msg_exp = await self.repo.add_bet_option(pool_exp.id, 10, 100, "B")
        self.assertFalse(success_exp)
        self.assertIn("locked", msg_exp)

    async def test_place_wager_validation(self):
        pool = await self.repo.create_bet_pool(10, 100, "Bet", options=["A", "B"])
        await self.economy_repo.set_balance(user_id=1, guild_id=10, amount=500)

        # Invalid amount
        self.assertFalse(await self.repo.place_wager(pool.id, 1, 10, "A", 0))
        self.assertFalse(await self.repo.place_wager(pool.id, 1, 10, "A", -50))

        # Invalid option (not in pool)
        self.assertFalse(await self.repo.place_wager(pool.id, 1, 10, "NonExistent", 50))

        # Non-existent pool
        self.assertFalse(await self.repo.place_wager(9999, 1, 10, "A", 50))

    async def test_place_wager_insufficient_balance(self):
        pool = await self.repo.create_bet_pool(10, 100, "Bet", options=["A", "B"])
        await self.economy_repo.set_balance(user_id=1, guild_id=10, amount=50)

        # Try to wager more than balance
        success = await self.repo.place_wager(pool.id, 1, 10, "A", 100)
        self.assertFalse(success)
        self.assertEqual(await self.economy_repo.get_balance(1, 10), 50)
        wagers = await self.repo.get_pool_wagers(pool.id, 10)
        self.assertEqual(len(wagers), 0)

    async def test_place_wager_success_and_increment(self):
        pool = await self.repo.create_bet_pool(10, 100, "Bet", options=["A", "B"])
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
        success2 = await self.repo.place_wager(pool.id, 1, 10, "a", 50)
        self.assertTrue(success2)
        self.assertEqual(await self.economy_repo.get_balance(1, 10), 350)

        wagers_after = await self.repo.get_pool_wagers(pool.id, 10)
        self.assertEqual(len(wagers_after), 1)
        self.assertEqual(wagers_after[0].amount, 150)

    async def test_place_wager_opposite_side_rejection(self):
        pool = await self.repo.create_bet_pool(10, 100, "Bet", options=["A", "B"])
        await self.economy_repo.set_balance(user_id=1, guild_id=10, amount=500)

        # First wager on A
        self.assertTrue(await self.repo.place_wager(pool.id, 1, 10, "A", 100))

        # Attempt wager on B should be rejected
        self.assertFalse(await self.repo.place_wager(pool.id, 1, 10, "B", 50))
        # Balance should still be 400
        self.assertEqual(await self.economy_repo.get_balance(1, 10), 400)

    async def test_place_wager_closed_or_locked_or_expired_rejection(self):
        pool = await self.repo.create_bet_pool(10, 100, "Bet", options=["A", "B"])
        await self.economy_repo.set_balance(user_id=1, guild_id=10, amount=500)

        # Cancel pool
        await self.repo.cancel_bet_pool(pool.id, 10)
        self.assertFalse(await self.repo.place_wager(pool.id, 1, 10, "A", 100))

        # Locked pool
        pool2 = await self.repo.create_bet_pool(10, 100, "Bet 2", options=["A", "B"])
        await self.repo.lock_bet_pool(pool2.id, 10)
        self.assertFalse(await self.repo.place_wager(pool2.id, 1, 10, "A", 100))

        # Expired pool
        past_time = datetime.now(timezone.utc) - timedelta(minutes=10)
        pool3 = await self.repo.create_bet_pool(10, 100, "Bet 3", options=["A", "B"], locks_at=past_time)
        self.assertFalse(await self.repo.place_wager(pool3.id, 1, 10, "A", 100))
        updated_pool3 = await self.repo.get_bet_pool(pool3.id, 10)
        self.assertTrue(updated_pool3.is_locked)  # type: ignore[union-attr]

    async def test_lock_bet_pool(self):
        pool = await self.repo.create_bet_pool(10, 100, "Bet", options=["A", "B"])
        self.assertFalse(pool.is_locked)

        success = await self.repo.lock_bet_pool(pool.id, 10)
        self.assertTrue(success)

        updated = await self.repo.get_bet_pool(pool.id, 10)
        self.assertTrue(updated.is_locked)  # type: ignore[union-attr]

        # Cannot lock already locked pool
        self.assertFalse(await self.repo.lock_bet_pool(pool.id, 10))

    async def test_auto_lock_expired_pools(self):
        past_time = datetime.now(timezone.utc) - timedelta(minutes=10)
        future_time = datetime.now(timezone.utc) + timedelta(minutes=30)

        p1 = await self.repo.create_bet_pool(10, 100, "P1", options=["A"], locks_at=past_time)
        p2 = await self.repo.create_bet_pool(10, 100, "P2", options=["A"], locks_at=future_time)
        p3 = await self.repo.create_bet_pool(10, 100, "P3", options=["A"], locks_at=None)

        expired = await self.repo.auto_lock_expired_pools()
        self.assertEqual(len(expired), 1)
        self.assertEqual(expired[0].id, p1.id)

        p1_after = await self.repo.get_bet_pool(p1.id, 10)
        p2_after = await self.repo.get_bet_pool(p2.id, 10)
        p3_after = await self.repo.get_bet_pool(p3.id, 10)
        self.assertTrue(p1_after.is_locked)  # type: ignore[union-attr]
        self.assertFalse(p2_after.is_locked)  # type: ignore[union-attr]
        self.assertFalse(p3_after.is_locked)  # type: ignore[union-attr]

    async def test_resolve_bet_pool_proportional_payout(self):
        pool = await self.repo.create_bet_pool(10, 100, "Bet", options=["Option A", "Option B"])
        await self.economy_repo.set_balance(1, 10, 100)
        await self.economy_repo.set_balance(2, 10, 100)
        await self.economy_repo.set_balance(3, 10, 200)

        await self.repo.place_wager(pool.id, 1, 10, "Option A", 100)
        await self.repo.place_wager(pool.id, 2, 10, "Option A", 100)
        await self.repo.place_wager(pool.id, 3, 10, "Option B", 200)

        self.assertEqual(await self.economy_repo.get_balance(1, 10), 0)
        self.assertEqual(await self.economy_repo.get_balance(2, 10), 0)
        self.assertEqual(await self.economy_repo.get_balance(3, 10), 0)

        payouts = await self.repo.resolve_bet_pool(pool.id, 10, "option a")
        self.assertIsNotNone(payouts)
        self.assertEqual(payouts, {1: 200, 2: 200})

        self.assertEqual(await self.economy_repo.get_balance(1, 10), 200)
        self.assertEqual(await self.economy_repo.get_balance(2, 10), 200)
        self.assertEqual(await self.economy_repo.get_balance(3, 10), 0)

        updated_pool = await self.repo.get_bet_pool(pool.id, 10)
        self.assertFalse(updated_pool.is_open)  # type: ignore[union-attr]
        self.assertTrue(updated_pool.is_locked)  # type: ignore[union-attr]
        self.assertEqual(updated_pool.winning_option, "option a")  # type: ignore[union-attr]

        # Cannot resolve again
        self.assertIsNone(await self.repo.resolve_bet_pool(pool.id, 10, "Option A"))

    async def test_resolve_bet_pool_integer_division_precision(self):
        pool = await self.repo.create_bet_pool(10, 100, "Bet", options=["A", "B"])
        await self.economy_repo.set_balance(1, 10, 10_000_000_000)
        await self.economy_repo.set_balance(2, 10, 20_000_000_000)

        await self.repo.place_wager(pool.id, 1, 10, "A", 10_000_000_000)
        await self.repo.place_wager(pool.id, 2, 10, "B", 20_000_000_000)

        payouts = await self.repo.resolve_bet_pool(pool.id, 10, "A")
        self.assertEqual(payouts, {1: 30_000_000_000})
        self.assertEqual(await self.economy_repo.get_balance(1, 10), 30_000_000_000)

    async def test_resolve_bet_pool_zero_winners_refunds(self):
        pool = await self.repo.create_bet_pool(10, 100, "Bet", options=["Option A", "Option B"])
        await self.economy_repo.set_balance(1, 10, 100)
        await self.repo.place_wager(pool.id, 1, 10, "Option A", 100)

        # Resolving with Option B when nobody bet on Option B -> full refund
        payouts = await self.repo.resolve_bet_pool(pool.id, 10, "Option B")
        self.assertEqual(payouts, {})
        self.assertEqual(await self.economy_repo.get_balance(1, 10), 100)

        updated_pool = await self.repo.get_bet_pool(pool.id, 10)
        self.assertFalse(updated_pool.is_open)  # type: ignore[union-attr]
        self.assertEqual(updated_pool.winning_option, "Option B")  # type: ignore[union-attr]

    async def test_cancel_bet_pool_refunds_all(self):
        pool = await self.repo.create_bet_pool(10, 100, "Bet", options=["A", "B"])
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

    async def test_get_all_open_bet_pools(self):
        p1 = await self.repo.create_bet_pool(10, 100, "Bet G1", options=["A"])
        p2 = await self.repo.create_bet_pool(20, 100, "Bet G2", options=["A"])
        p3 = await self.repo.create_bet_pool(30, 100, "Bet G3 Closed", options=["A"])
        await self.repo.cancel_bet_pool(p3.id, 30)

        all_open = await self.repo.get_all_open_bet_pools()
        all_ids = [p.id for p in all_open]
        self.assertIn(p1.id, all_ids)
        self.assertIn(p2.id, all_ids)
        self.assertNotIn(p3.id, all_ids)


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
        self.mock_client.wait_until_ready = AsyncMock()
        self.mock_client.db = MagicMock()
        self.mock_economy_repo = MagicMock(spec=EconomyRepository)
        self.mock_gambling_repo = MagicMock(spec=GamblingRepository)
        self.cog = Gambling(
            self.mock_client,
            gambling_repo=self.mock_gambling_repo,
            economy_repo=self.mock_economy_repo,
        )
        for cmd in [self.cog.bet, self.cog.bet_list]:
            cmd.cog = self.cog

    def tearDown(self):
        if self.cog.auto_lock_task.is_running():
            self.cog.auto_lock_task.cancel()
        self.logger_patcher.stop()

    def _make_ctx(self, user_id: int = 1, guild_id: int = 10, is_admin: bool = False, roles=None):
        ctx = MagicMock()
        ctx.author = MagicMock(id=user_id, mention=f"<@{user_id}>", roles=roles or [])
        ctx.author.guild_permissions = MagicMock(administrator=is_admin)
        ctx.guild = MagicMock(id=guild_id, emojis=[])
        ctx.response.send_message = AsyncMock()
        ctx.response.send_modal = AsyncMock()
        return ctx

    def _make_interaction(self, user_id: int = 1, guild_id: int = 10, is_admin: bool = False, roles=None):
        inter = MagicMock(spec=discord.Interaction)
        inter.user = MagicMock(id=user_id, mention=f"<@{user_id}>", roles=roles or [])
        inter.user.guild_permissions = MagicMock(administrator=is_admin)
        inter.guild = MagicMock(id=guild_id, emojis=[])
        inter.channel = MagicMock()
        inter.channel.id = 555
        inter.channel.send = AsyncMock()
        inter.response.send_message = AsyncMock()
        inter.response.send_modal = AsyncMock()
        inter.response.edit_message = AsyncMock()
        return inter

    async def test_bet_command_sends_modal(self):
        ctx = self._make_ctx()
        await self.cog.bet(ctx)
        ctx.response.send_modal.assert_called_once()
        modal = ctx.response.send_modal.call_args[0][0]
        self.assertIsInstance(modal, BetCreateModal)

    async def test_bet_create_modal_empty_title(self):
        modal = BetCreateModal(self.cog)
        modal.title_input = MagicMock(value="   ")
        modal.options_input = MagicMock(value="A\nB")
        modal.duration_input = MagicMock(value="30m")

        inter = self._make_interaction()
        await modal.callback(inter)
        inter.response.send_message.assert_called_once()
        self.assertIn("cannot be empty", inter.response.send_message.call_args[0][0])

    async def test_bet_create_modal_invalid_duration(self):
        modal = BetCreateModal(self.cog)
        modal.title_input = MagicMock(value="Valid Title")
        modal.options_input = MagicMock(value="A\nB")
        modal.duration_input = MagicMock(value="invalid_duration")

        inter = self._make_interaction()
        await modal.callback(inter)
        inter.response.send_message.assert_called_once()
        self.assertIn("Invalid duration", inter.response.send_message.call_args[0][0])

    async def test_bet_create_modal_option_too_long(self):
        modal = BetCreateModal(self.cog)
        modal.title_input = MagicMock(value="Valid Title")
        modal.options_input = MagicMock(value="A" * 105)
        modal.duration_input = MagicMock(value="")

        inter = self._make_interaction()
        await modal.callback(inter)
        inter.response.send_message.assert_called_once()
        self.assertIn("exceeds maximum length of 100", inter.response.send_message.call_args[0][0])

    async def test_bet_create_modal_success_shows_setup_view(self):
        modal = BetCreateModal(self.cog)
        modal.title_input = MagicMock(value="Race winner")
        modal.options_input = MagicMock(value="Dragon 1\nDragon 2")
        modal.duration_input = MagicMock(value="1h")

        inter = self._make_interaction()
        await modal.callback(inter)
        inter.response.send_message.assert_called_once()
        embed = inter.response.send_message.call_args[1]["embed"]
        view = inter.response.send_message.call_args[1]["view"]
        self.assertIn("Race winner", embed.title)
        self.assertIsInstance(view, BetSetupView)

    async def test_bet_setup_view_toggle_custom_options(self):
        view = BetSetupView(self.cog, "Title", ["A", "B"], timedelta(hours=1))
        self.assertTrue(view.allow_custom)

        inter = self._make_interaction()
        await view._on_toggle_custom(inter)
        self.assertFalse(view.allow_custom)
        inter.response.edit_message.assert_called_once()

    async def test_bet_setup_view_toggle_custom_options_locked_for_zero_options(self):
        view = BetSetupView(self.cog, "Title", [], None)
        self.assertTrue(view.allow_custom)

        inter = self._make_interaction()
        await view._on_toggle_custom(inter)
        # Should stay True and notify user
        self.assertTrue(view.allow_custom)
        inter.response.send_message.assert_called_once()
        self.assertIn("must be allowed", inter.response.send_message.call_args[0][0])

    async def test_bet_setup_view_publish_success(self):
        view = BetSetupView(self.cog, "Grand Tournament", ["Knight A", "Knight B"], timedelta(hours=2))
        inter = self._make_interaction(user_id=100, guild_id=10)

        created_pool = BetPool(
            id=42,
            guild_id=10,
            channel_id=None,
            message_id=None,
            creator_id=100,
            title="Grand Tournament",
            allow_custom_options=True,
            is_open=True,
            is_locked=False,
            locks_at=datetime.now(timezone.utc) + timedelta(hours=2),
        )
        self.mock_gambling_repo.create_bet_pool = AsyncMock(return_value=created_pool)
        self.mock_gambling_repo.get_pool_options = AsyncMock(
            return_value=[
                BetOption(id=1, pool_id=42, label="Knight A", creator_id=100),
                BetOption(id=2, pool_id=42, label="Knight B", creator_id=100),
            ]
        )
        self.mock_gambling_repo.set_pool_message = AsyncMock(return_value=True)

        sent_msg = MagicMock()
        sent_msg.id = 999
        sent_msg.jump_url = "https://discord.com/channels/10/555/999"
        inter.channel.send = AsyncMock(return_value=sent_msg)

        await view._on_publish(inter)
        self.mock_gambling_repo.create_bet_pool.assert_called_once()
        inter.channel.send.assert_called_once()
        self.mock_gambling_repo.set_pool_message.assert_called_once_with(42, 10, 555, 999)
        inter.response.edit_message.assert_called_once()
        self.assertIn("published successfully", inter.response.edit_message.call_args[1]["content"])

    async def test_bet_pool_view_components(self):
        pool_open = BetPool(
            id=1,
            guild_id=10,
            creator_id=100,
            title="T",
            allow_custom_options=True,
            is_open=True,
            is_locked=False,
        )
        options = [BetOption(id=1, pool_id=1, label="A", creator_id=100)]
        view_open = BetPoolView(self.cog, pool_open, options)
        # Should have Select, Add Option button, Lock button, Resolve button, Cancel button
        self.assertEqual(len(view_open.children), 5)

        pool_locked = BetPool(
            id=1,
            guild_id=10,
            creator_id=100,
            title="T",
            allow_custom_options=True,
            is_open=True,
            is_locked=True,
        )
        view_locked = BetPoolView(self.cog, pool_locked, options)
        # Should only have Resolve button and Cancel button
        self.assertEqual(len(view_locked.children), 2)

    async def test_lock_button_unauthorized(self):
        btn = LockButton(self.cog, pool_id=1, creator_id=100)
        inter = self._make_interaction(user_id=999, is_admin=False)
        self.mock_client.db.get_setting = AsyncMock(return_value=None)

        await btn.callback(inter)
        inter.response.send_message.assert_called_once()
        self.assertIn("Only the creator or a team member", inter.response.send_message.call_args[0][0])
        self.mock_gambling_repo.lock_bet_pool.assert_not_called()

    async def test_lock_button_authorized(self):
        btn = LockButton(self.cog, pool_id=1, creator_id=100)
        inter = self._make_interaction(user_id=100, guild_id=10)
        self.mock_gambling_repo.lock_bet_pool = AsyncMock(return_value=True)
        mock_update = AsyncMock()
        setattr(self.cog, "_update_bet_message", mock_update)

        await btn.callback(inter)
        self.mock_gambling_repo.lock_bet_pool.assert_called_once_with(1, 10)
        inter.response.send_message.assert_called_once()
        self.assertIn("now locked", inter.response.send_message.call_args[0][0])
        mock_update.assert_called_once_with(1, 10)

    async def test_cancel_button_authorized(self):
        btn = CancelButton(self.cog, pool_id=1, creator_id=100)
        inter = self._make_interaction(user_id=100, guild_id=10)
        self.mock_gambling_repo.cancel_bet_pool = AsyncMock(return_value=True)
        mock_update = AsyncMock()
        setattr(self.cog, "_update_bet_message", mock_update)

        await btn.callback(inter)
        self.mock_gambling_repo.cancel_bet_pool.assert_called_once_with(1, 10)
        inter.response.send_message.assert_called_once()
        self.assertIn("cancelled and all wagers refunded", inter.response.send_message.call_args[0][0])
        mock_update.assert_called_once_with(1, 10)

    async def test_resolve_button_opens_view(self):
        btn = ResolveButton(self.cog, pool_id=1, creator_id=100, options=[])
        inter = self._make_interaction(user_id=100)
        self.mock_gambling_repo.get_pool_options = AsyncMock(return_value=[])

        await btn.callback(inter)
        inter.response.send_message.assert_called_once()
        view = inter.response.send_message.call_args[1]["view"]
        self.assertIsInstance(view, ResolveBetView)

    async def test_place_wager_modal_success(self):
        modal = PlaceWagerModal(self.cog, pool_id=1, option_label="Option A")
        modal.amount_input = MagicMock(value="150")

        inter = self._make_interaction(user_id=5, guild_id=10)
        pool = BetPool(id=1, guild_id=10, creator_id=100, title="T", is_open=True, is_locked=False)
        self.mock_gambling_repo.get_bet_pool = AsyncMock(return_value=pool)
        self.mock_gambling_repo.get_pool_wagers = AsyncMock(return_value=[])
        self.mock_economy_repo.get_balance = AsyncMock(return_value=500)
        self.mock_gambling_repo.place_wager = AsyncMock(return_value=True)
        mock_update = AsyncMock()
        setattr(self.cog, "_update_bet_message", mock_update)

        await modal.callback(inter)
        self.mock_gambling_repo.place_wager.assert_called_once_with(1, 5, 10, "Option A", 150)
        inter.response.send_message.assert_called_once()
        self.assertIn("Successfully wagered", inter.response.send_message.call_args[0][0])
        mock_update.assert_called_once_with(1, 10)

    async def test_place_wager_modal_conflicting_option(self):
        modal = PlaceWagerModal(self.cog, pool_id=1, option_label="Option B")
        modal.amount_input = MagicMock(value="150")

        inter = self._make_interaction(user_id=5, guild_id=10)
        pool = BetPool(id=1, guild_id=10, creator_id=100, title="T", is_open=True, is_locked=False)
        self.mock_gambling_repo.get_bet_pool = AsyncMock(return_value=pool)
        existing_wager = BetWager(id=1, pool_id=1, user_id=5, guild_id=10, choice="Option A", amount=100)
        self.mock_gambling_repo.get_pool_wagers = AsyncMock(return_value=[existing_wager])

        await modal.callback(inter)
        inter.response.send_message.assert_called_once()
        self.assertIn("already wagered on 'Option A'", inter.response.send_message.call_args[0][0])
        self.mock_gambling_repo.place_wager.assert_not_called()

    async def test_add_custom_option_modal_success(self):
        modal = AddCustomOptionModal(self.cog, pool_id=1)
        modal.label_input = MagicMock(value="Dark Horse")
        modal.amount_input = MagicMock(value="200")

        inter = self._make_interaction(user_id=5, guild_id=10)
        created_opt = BetOption(id=10, pool_id=1, label="Dark Horse", creator_id=5)
        self.mock_gambling_repo.add_bet_option = AsyncMock(return_value=(True, created_opt, "Option added."))
        self.mock_gambling_repo.get_pool_wagers = AsyncMock(return_value=[])
        self.mock_economy_repo.get_balance = AsyncMock(return_value=500)
        self.mock_gambling_repo.place_wager = AsyncMock(return_value=True)
        mock_update = AsyncMock()
        setattr(self.cog, "_update_bet_message", mock_update)

        await modal.callback(inter)
        self.mock_gambling_repo.add_bet_option.assert_called_once_with(1, 10, 5, "Dark Horse")
        self.mock_gambling_repo.place_wager.assert_called_once_with(1, 5, 10, "Dark Horse", 200)
        inter.response.send_message.assert_called_once()
        self.assertIn("Successfully added option", inter.response.send_message.call_args[0][0])
        mock_update.assert_called_once_with(1, 10)

    async def test_custom_outcome_modal_resolves_pool(self):
        modal = CustomOutcomeModal(self.cog, pool_id=1)
        modal.outcome_input = MagicMock(value="Tie / Draw")

        inter = self._make_interaction(user_id=100, guild_id=10)
        self.mock_gambling_repo.resolve_bet_pool = AsyncMock(return_value={5: 600})
        mock_update = AsyncMock()
        setattr(self.cog, "_update_bet_message", mock_update)

        await modal.callback(inter)
        self.mock_gambling_repo.resolve_bet_pool.assert_called_once_with(1, 10, "Tie / Draw")
        inter.response.send_message.assert_called_once()
        self.assertIn("Distributed", inter.response.send_message.call_args[0][0])
        mock_update.assert_called_once_with(1, 10)

    async def test_bet_list_empty(self):
        ctx = self._make_ctx()
        self.mock_gambling_repo.get_open_bet_pools = AsyncMock(return_value=[])

        await self.cog.bet_list(ctx)
        self.assertIn("no open bet pools", ctx.response.send_message.call_args[0][0])

    async def test_bet_list_with_pools_and_jump_links(self):
        ctx = self._make_ctx()
        pool = BetPool(
            id=1,
            guild_id=10,
            channel_id=555,
            message_id=999,
            creator_id=100,
            title="Match 1",
            is_open=True,
            is_locked=False,
        )
        self.mock_gambling_repo.get_open_bet_pools = AsyncMock(return_value=[pool])
        wager = BetWager(id=1, pool_id=1, user_id=2, guild_id=10, choice="Option A", amount=150)
        self.mock_gambling_repo.get_pool_wagers = AsyncMock(return_value=[wager])

        await self.cog.bet_list(ctx)
        embed = ctx.response.send_message.call_args[1]["embed"]
        self.assertEqual(embed.title, "Active Prediction Bet Pools")
        self.assertEqual(len(embed.fields), 1)
        self.assertIn("Jump to Bet", embed.fields[0].value)

    async def test_bet_list_truncates_at_10_pools(self):
        ctx = self._make_ctx()
        pools = [
            BetPool(
                id=i,
                guild_id=10,
                creator_id=100,
                title=f"Match {i}",
                is_open=True,
                is_locked=False,
            )
            for i in range(1, 13)
        ]
        self.mock_gambling_repo.get_open_bet_pools = AsyncMock(return_value=pools)
        self.mock_gambling_repo.get_pool_wagers = AsyncMock(return_value=[])

        await self.cog.bet_list(ctx)
        embed = ctx.response.send_message.call_args[1]["embed"]
        self.assertEqual(len(embed.fields), 10)
        self.assertIn("Showing 10 of 12", embed.footer.text)

    async def test_auto_lock_task(self):
        expired_pool = BetPool(id=1, guild_id=10, creator_id=100, title="T", is_open=True, is_locked=True)
        self.mock_gambling_repo.auto_lock_expired_pools = AsyncMock(return_value=[expired_pool])
        mock_update = AsyncMock()
        setattr(self.cog, "_update_bet_message", mock_update)

        # Execute one iteration of the task directly
        await self.cog.auto_lock_task()
        self.mock_gambling_repo.auto_lock_expired_pools.assert_called_once()
        mock_update.assert_called_once_with(1, 10)

    async def test_on_start_done_registers_views(self):
        pool_with_msg = BetPool(
            id=1,
            guild_id=10,
            channel_id=555,
            message_id=999,
            creator_id=100,
            title="Pool With Message",
            is_open=True,
            is_locked=False,
        )
        pool_no_msg = BetPool(
            id=2,
            guild_id=10,
            channel_id=None,
            message_id=None,
            creator_id=100,
            title="Pool Without Message",
            is_open=True,
            is_locked=False,
        )
        self.mock_gambling_repo.get_all_open_bet_pools = AsyncMock(return_value=[pool_with_msg, pool_no_msg])
        self.mock_gambling_repo.get_pool_options = AsyncMock(return_value=[])

        await self.cog.on_start_done()

        self.mock_client.add_view.assert_called_once()
        call_kwargs = self.mock_client.add_view.call_args[1]
        self.assertEqual(call_kwargs.get("message_id"), 999)
        self.assertIsInstance(self.mock_client.add_view.call_args[0][0], BetPoolView)
