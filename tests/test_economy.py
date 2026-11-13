from datetime import datetime
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from extensions.economy.economy import Economy
from extensions.economy.models import format_scales, get_dragon_scale_emoji
from extensions.economy.repository import EconomyRepository
from utils.bot import Bot
from utils.orm_database import Base, ORMDataBase
from utils.utils import VersionInfo


class MockEmoji:
    def __init__(self, name: str, emoji_str: str):
        self.name = name
        self.emoji_str = emoji_str

    def __str__(self) -> str:
        return self.emoji_str


def mock_entity(entity_id: int, **kwargs) -> SimpleNamespace:
    return SimpleNamespace(id=entity_id, **kwargs)


class TestFormatScales(unittest.TestCase):
    def test_format_scales_default_fallback(self):
        result = format_scales(10)
        self.assertEqual(result, "10 🐉 Dragon Scales")

    def test_format_scales_singular(self):
        result = format_scales(1)
        self.assertEqual(result, "1 🐉 Dragon Scale")

    def test_format_scales_zero(self):
        result = format_scales(0)
        self.assertEqual(result, "0 🐉 Dragon Scales")

    def test_format_scales_thousands_separator(self):
        result = format_scales(1234567)
        self.assertEqual(result, "1,234,567 🐉 Dragon Scales")

    def test_format_scales_custom_emoji_present(self):
        mock_emoji = MockEmoji("dragon_scale", "<:dragon_scale:987654321>")
        mock_guild = SimpleNamespace(emojis=[mock_emoji])

        result = format_scales(42, mock_guild)  # type: ignore[arg-type]
        self.assertEqual(result, "42 <:dragon_scale:987654321> Dragon Scales")

    def test_format_scales_custom_emoji_absent(self):
        other_emoji = MockEmoji("gold_coin", "<:gold_coin:123>")
        mock_guild = SimpleNamespace(emojis=[other_emoji])

        result = format_scales(5, mock_guild)  # type: ignore[arg-type]
        self.assertEqual(result, "5 🐉 Dragon Scales")

    def test_format_scales_app_emoji_fallback(self):
        mock_guild = SimpleNamespace(emojis=[])
        mock_bot = SimpleNamespace(app_emojis={"dragon_scale": "<:dragon_scale:111222333>"})

        result = format_scales(25, mock_guild, mock_bot)  # type: ignore[arg-type]
        self.assertEqual(result, "25 <:dragon_scale:111222333> Dragon Scales")

    def test_get_dragon_scale_emoji_guild_overrides_app_emoji(self):
        guild_emoji = MockEmoji("dragon_scale", "<:dragon_scale:999>")
        mock_guild = SimpleNamespace(emojis=[guild_emoji])
        mock_bot = SimpleNamespace(app_emojis={"dragon_scale": "<:dragon_scale:111>"})

        result = get_dragon_scale_emoji(mock_guild, mock_bot)  # type: ignore[arg-type]
        self.assertEqual(result, "<:dragon_scale:999>")

    def test_get_dragon_scale_emoji_ignores_non_dict_app_emojis(self):
        mock_guild = SimpleNamespace(emojis=[])
        mock_bot = MagicMock()

        result = get_dragon_scale_emoji(mock_guild, mock_bot)  # type: ignore[arg-type]
        self.assertEqual(result, "🐉")


class TestBotApplicationEmoji(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        with (
            patch("utils.bot.CustomLogger"),
            patch("utils.bot.ORMDataBase"),
            patch("utils.bot.ShortTermStorage"),
            patch("utils.bot.ipc.Server"),
        ):
            self.bot = Bot(version=VersionInfo(3, 0, 1, ""), command_prefix="!")

    async def test_ensure_application_emoji_returns_cached(self):
        self.bot.app_emojis["dragon_scale"] = "<:dragon_scale:100>"
        self.bot.fetch_emojis = AsyncMock()  # type: ignore[method-assign]
        self.bot.create_emoji = AsyncMock()  # type: ignore[method-assign]

        result = await self.bot.ensure_application_emoji("dragon_scale", "assets/dragon_scale.png")
        self.assertEqual(result, "<:dragon_scale:100>")
        self.bot.fetch_emojis.assert_not_called()
        self.bot.create_emoji.assert_not_called()

    async def test_ensure_application_emoji_fetches_and_caches_existing(self):
        existing = MockEmoji("dragon_scale", "<:dragon_scale:200>")
        self.bot.fetch_emojis = AsyncMock(return_value=[existing])  # type: ignore[method-assign]
        self.bot.create_emoji = AsyncMock()  # type: ignore[method-assign]

        result = await self.bot.ensure_application_emoji("dragon_scale", "assets/dragon_scale.png")
        self.assertEqual(result, "<:dragon_scale:200>")
        self.assertEqual(self.bot.app_emojis["dragon_scale"], "<:dragon_scale:200>")
        self.bot.fetch_emojis.assert_called_once()
        self.bot.create_emoji.assert_not_called()

    async def test_ensure_application_emoji_creates_when_missing(self):
        created = MockEmoji("dragon_scale", "<:dragon_scale:300>")
        self.bot.fetch_emojis = AsyncMock(return_value=[])  # type: ignore[method-assign]
        self.bot.create_emoji = AsyncMock(return_value=created)  # type: ignore[method-assign]

        with tempfile.TemporaryDirectory() as tmpdir:
            icon_file = Path(tmpdir) / "dragon_scale.png"
            icon_file.write_bytes(b"fake-png-bytes")
            result = await self.bot.ensure_application_emoji("dragon_scale", icon_file)

        self.assertEqual(result, "<:dragon_scale:300>")
        self.assertEqual(self.bot.app_emojis["dragon_scale"], "<:dragon_scale:300>")
        self.bot.create_emoji.assert_called_once_with(name="dragon_scale", image=b"fake-png-bytes")

    async def test_ensure_application_emoji_handles_missing_asset_and_api_error(self):
        self.bot.fetch_emojis = AsyncMock(return_value=[])  # type: ignore[method-assign]
        self.bot.create_emoji = AsyncMock()  # type: ignore[method-assign]

        missing_res = await self.bot.ensure_application_emoji("dragon_scale", "nonexistent/dragon_scale.png")
        self.assertIsNone(missing_res)
        self.bot.create_emoji.assert_not_called()

        self.bot.fetch_emojis = AsyncMock(side_effect=RuntimeError("Discord API down"))  # type: ignore[method-assign]
        error_res = await self.bot.ensure_application_emoji("dragon_scale", "assets/dragon_scale.png")
        self.assertIsNone(error_res)


class TestEconomyRepository(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.session_maker: async_sessionmaker[AsyncSession] = async_sessionmaker(self.engine, expire_on_commit=False)
        ORMDataBase._discover_models(SimpleNamespace(logger=None))  # type: ignore[arg-type]
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.repo = EconomyRepository(self.session_maker)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_get_balance_defaults_to_zero(self):
        balance = await self.repo.get_balance(user_id=1, guild_id=10)
        self.assertEqual(balance, 0)

    async def test_add_balance_creates_row_and_increments(self):
        bal1 = await self.repo.add_balance(user_id=1, guild_id=10, amount=100)
        self.assertEqual(bal1, 100)

        bal2 = await self.repo.add_balance(user_id=1, guild_id=10, amount=50)
        self.assertEqual(bal2, 150)

        fetch_bal = await self.repo.get_balance(user_id=1, guild_id=10)
        self.assertEqual(fetch_bal, 150)

    async def test_add_balance_negative_raises_value_error(self):
        with self.assertRaises(ValueError):
            await self.repo.add_balance(user_id=1, guild_id=10, amount=-10)

    async def test_remove_balance_success_and_insufficient_funds(self):
        await self.repo.set_balance(user_id=1, guild_id=10, amount=100)

        # Insufficient funds
        success_over = await self.repo.remove_balance(user_id=1, guild_id=10, amount=150)
        self.assertFalse(success_over)
        self.assertEqual(await self.repo.get_balance(user_id=1, guild_id=10), 100)

        # Amount 0
        success_zero = await self.repo.remove_balance(user_id=1, guild_id=10, amount=0)
        self.assertFalse(success_zero)
        self.assertEqual(await self.repo.get_balance(user_id=1, guild_id=10), 100)

        # Valid deduction
        success_deduct = await self.repo.remove_balance(user_id=1, guild_id=10, amount=40)
        self.assertTrue(success_deduct)
        self.assertEqual(await self.repo.get_balance(user_id=1, guild_id=10), 60)

        # Exact deduction
        success_exact = await self.repo.remove_balance(user_id=1, guild_id=10, amount=60)
        self.assertTrue(success_exact)
        self.assertEqual(await self.repo.get_balance(user_id=1, guild_id=10), 0)

    async def test_remove_balance_nonexistent_user(self):
        success = await self.repo.remove_balance(user_id=999, guild_id=10, amount=10)
        self.assertFalse(success)

    async def test_remove_balance_negative_raises_value_error(self):
        with self.assertRaises(ValueError):
            await self.repo.remove_balance(user_id=1, guild_id=10, amount=-5)

    async def test_set_balance_creates_and_updates(self):
        # Create
        new_bal = await self.repo.set_balance(user_id=1, guild_id=10, amount=250)
        self.assertEqual(new_bal, 250)
        self.assertEqual(await self.repo.get_balance(user_id=1, guild_id=10), 250)

        # Update
        updated_bal = await self.repo.set_balance(user_id=1, guild_id=10, amount=50)
        self.assertEqual(updated_bal, 50)
        self.assertEqual(await self.repo.get_balance(user_id=1, guild_id=10), 50)

    async def test_set_balance_negative_raises_value_error(self):
        with self.assertRaises(ValueError):
            await self.repo.set_balance(user_id=1, guild_id=10, amount=-1)

    async def test_transfer_balance_atomic_success(self):
        await self.repo.set_balance(user_id=1, guild_id=10, amount=200)
        await self.repo.set_balance(user_id=2, guild_id=10, amount=50)

        transferred = await self.repo.transfer_balance(sender_id=1, receiver_id=2, guild_id=10, amount=80)
        self.assertTrue(transferred)
        self.assertEqual(await self.repo.get_balance(user_id=1, guild_id=10), 120)
        self.assertEqual(await self.repo.get_balance(user_id=2, guild_id=10), 130)

    async def test_transfer_balance_creates_receiver_wallet(self):
        await self.repo.set_balance(user_id=1, guild_id=10, amount=100)

        transferred = await self.repo.transfer_balance(sender_id=1, receiver_id=2, guild_id=10, amount=40)
        self.assertTrue(transferred)
        self.assertEqual(await self.repo.get_balance(user_id=1, guild_id=10), 60)
        self.assertEqual(await self.repo.get_balance(user_id=2, guild_id=10), 40)

    async def test_transfer_balance_insufficient_funds(self):
        await self.repo.set_balance(user_id=1, guild_id=10, amount=30)
        transferred = await self.repo.transfer_balance(sender_id=1, receiver_id=2, guild_id=10, amount=50)
        self.assertFalse(transferred)
        self.assertEqual(await self.repo.get_balance(user_id=1, guild_id=10), 30)
        self.assertEqual(await self.repo.get_balance(user_id=2, guild_id=10), 0)

    async def test_transfer_balance_invalid_inputs(self):
        await self.repo.set_balance(user_id=1, guild_id=10, amount=100)

        # Same user
        self.assertFalse(await self.repo.transfer_balance(sender_id=1, receiver_id=1, guild_id=10, amount=50))
        # Amount 0
        self.assertFalse(await self.repo.transfer_balance(sender_id=1, receiver_id=2, guild_id=10, amount=0))
        # Amount negative
        self.assertFalse(await self.repo.transfer_balance(sender_id=1, receiver_id=2, guild_id=10, amount=-10))

    async def test_get_leaderboard(self):
        guild_id = 100
        await self.repo.set_balance(user_id=1, guild_id=guild_id, amount=500)
        await self.repo.set_balance(user_id=2, guild_id=guild_id, amount=100)
        await self.repo.set_balance(user_id=3, guild_id=guild_id, amount=1000)
        await self.repo.set_balance(user_id=4, guild_id=guild_id, amount=0)  # should not appear
        await self.repo.set_balance(user_id=5, guild_id=200, amount=9999)  # different guild

        leaderboard = await self.repo.get_leaderboard(guild_id=guild_id, limit=10)
        self.assertEqual(len(leaderboard), 3)
        self.assertEqual(leaderboard[0].user_id, 3)
        self.assertEqual(leaderboard[0].balance, 1000)
        self.assertEqual(leaderboard[1].user_id, 1)
        self.assertEqual(leaderboard[1].balance, 500)
        self.assertEqual(leaderboard[2].user_id, 2)
        self.assertEqual(leaderboard[2].balance, 100)

        # Test limit
        limited = await self.repo.get_leaderboard(guild_id=guild_id, limit=2)
        self.assertEqual(len(limited), 2)
        self.assertEqual(limited[0].user_id, 3)
        self.assertEqual(limited[1].user_id, 1)


class TestEconomyCogMessageEarning(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.logger_patcher = patch("extensions.economy.economy.CustomLogger")
        self.logger_patcher.start()
        self.mock_client = MagicMock()
        self.mock_client.boot_time = datetime.now()
        self.mock_repo = MagicMock(spec=EconomyRepository)
        self.mock_repo.add_balance = AsyncMock()
        self.cog = Economy(self.mock_client, economy_repo=self.mock_repo)

    def tearDown(self):
        self.logger_patcher.stop()

    async def test_on_message_ignores_bot(self):
        msg = MagicMock()
        msg.author.bot = True
        msg.guild = MagicMock()
        msg.content = "Valid message"

        await self.cog.on_message(msg)
        self.mock_repo.add_balance.assert_not_called()

    async def test_on_message_ignores_dm(self):
        msg = MagicMock()
        msg.author.bot = False
        msg.guild = None
        msg.content = "Valid message"

        await self.cog.on_message(msg)
        self.mock_repo.add_balance.assert_not_called()

    async def test_on_message_ignores_short_message(self):
        msg = MagicMock()
        msg.author.bot = False
        msg.guild = MagicMock(id=10)
        msg.content = "hi"

        await self.cog.on_message(msg)
        self.mock_repo.add_balance.assert_not_called()

    async def test_on_message_anti_spam_duplicate_content(self):
        msg = MagicMock()
        msg.author.bot = False
        msg.author.id = 1
        msg.guild = MagicMock(id=10)
        msg.content = "Hello there dragons"

        with patch("random.randint", return_value=1):
            await self.cog.on_message(msg)
            self.assertEqual(self.mock_repo.add_balance.call_count, 1)

            # Send duplicate content
            await self.cog.on_message(msg)
            self.assertEqual(self.mock_repo.add_balance.call_count, 1)

    async def test_on_message_anti_spam_cooldown(self):
        msg1 = MagicMock()
        msg1.author.bot = False
        msg1.author.id = 1
        msg1.guild = MagicMock(id=10)
        msg1.content = "First message test"

        msg2 = MagicMock()
        msg2.author.bot = False
        msg2.author.id = 1
        msg2.guild = MagicMock(id=10)
        msg2.content = "Second message test"

        with patch("random.randint", return_value=1), patch("time.monotonic", side_effect=[100.0, 110.0, 175.0]):
            # First message at t=100.0
            await self.cog.on_message(msg1)
            self.assertEqual(self.mock_repo.add_balance.call_count, 1)

            # Second message at t=110.0 (within 60s cooldown)
            await self.cog.on_message(msg2)
            self.assertEqual(self.mock_repo.add_balance.call_count, 1)

            # Third message at t=175.0 (after cooldown: 175 - 100 = 75s > 60s)
            await self.cog.on_message(msg2)
            self.assertEqual(self.mock_repo.add_balance.call_count, 2)

    async def test_on_message_random_roll_zero_does_not_credit(self):
        msg = MagicMock()
        msg.author.bot = False
        msg.author.id = 1
        msg.guild = MagicMock(id=10)
        msg.content = "Random test roll"

        with patch("random.randint", return_value=0):
            await self.cog.on_message(msg)
            self.mock_repo.add_balance.assert_not_called()


class TestEconomyCogVoiceTime(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.logger_patcher = patch("extensions.economy.economy.CustomLogger")
        self.logger_patcher.start()
        self.mock_client = MagicMock()
        self.mock_client.boot_time = datetime.now()
        self.mock_repo = MagicMock(spec=EconomyRepository)
        self.mock_repo.add_balance = AsyncMock()
        self.cog = Economy(self.mock_client, economy_repo=self.mock_repo)

    def tearDown(self):
        self.logger_patcher.stop()

    def test_calculate_voice_scales(self):
        # 5 scales per hour (3600 seconds)
        self.assertEqual(self.cog._calculate_voice_scales(0), 0)
        self.assertEqual(self.cog._calculate_voice_scales(3600), 5)
        self.assertEqual(self.cog._calculate_voice_scales(7200), 10)
        self.assertEqual(self.cog._calculate_voice_scales(720), 1)  # 720 * 5 / 3600 = 1.0
        self.assertEqual(self.cog._calculate_voice_scales(1800), 2)  # round(2.5) == 2 in round-to-even

    async def test_on_start_done(self):
        mock_guild = MagicMock(id=100)
        afk_channel = MagicMock(id=999)
        mock_guild.afk_channel = afk_channel

        valid_channel = MagicMock(id=10)
        valid_member = MagicMock(bot=False, id=1, voice=MagicMock(self_deaf=False, deaf=False))
        deaf_member = MagicMock(bot=False, id=2, voice=MagicMock(self_deaf=True, deaf=False))
        bot_member = MagicMock(bot=True, id=3, voice=MagicMock(self_deaf=False, deaf=False))
        valid_channel.members = [valid_member, deaf_member, bot_member]

        afk_channel_vc = MagicMock(id=999)
        afk_member = MagicMock(bot=False, id=4, voice=MagicMock(self_deaf=False, deaf=False))
        afk_channel_vc.members = [afk_member]

        mock_guild.voice_channels = [valid_channel, afk_channel_vc]
        self.mock_client.guilds = [mock_guild]

        await self.cog.on_start_done()

        self.assertIn((100, 1), self.cog._voice_cache)
        self.assertNotIn((100, 2), self.cog._voice_cache)
        self.assertNotIn((100, 3), self.cog._voice_cache)
        self.assertNotIn((100, 4), self.cog._voice_cache)

    async def test_on_voice_state_update_join_and_leave(self):
        guild = MagicMock(id=100, afk_channel=None)
        channel = MagicMock(id=10, guild=guild)
        member = MagicMock(bot=False, id=1, guild=guild)

        # 1. Join voice
        before = MagicMock(channel=None, self_deaf=False, deaf=False)
        after = MagicMock(channel=channel, self_deaf=False, deaf=False)
        with patch("time.monotonic", return_value=1000.0):
            await self.cog.on_voice_state_update(member, before, after)
            self.assertIn((100, 1), self.cog._voice_cache)
            self.assertEqual(self.cog._voice_cache[(100, 1)], 1000.0)

        # 2. Leave voice after 1 hour (3600 seconds)
        before_leave = MagicMock(channel=channel, self_deaf=False, deaf=False)
        after_leave = MagicMock(channel=None, self_deaf=False, deaf=False)
        with patch("time.monotonic", return_value=4600.0):
            await self.cog.on_voice_state_update(member, before_leave, after_leave)
            self.assertNotIn((100, 1), self.cog._voice_cache)
            self.mock_repo.add_balance.assert_called_once_with(1, 100, 5)

    async def test_on_voice_state_update_deafen_and_undeafen(self):
        guild = MagicMock(id=100, afk_channel=None)
        channel = MagicMock(id=10, guild=guild)
        member = MagicMock(bot=False, id=1, guild=guild)

        # Start tracked
        self.cog._voice_cache[(100, 1)] = 1000.0

        # Deafen after 2 hours (7200 seconds)
        before = MagicMock(channel=channel, self_deaf=False, deaf=False)
        after = MagicMock(channel=channel, self_deaf=True, deaf=False)
        with patch("time.monotonic", return_value=8200.0):
            await self.cog.on_voice_state_update(member, before, after)
            self.assertNotIn((100, 1), self.cog._voice_cache)
            self.mock_repo.add_balance.assert_called_once_with(1, 100, 10)

        # Undeafen
        self.mock_repo.add_balance.reset_mock()
        before_und = MagicMock(channel=channel, self_deaf=True, deaf=False)
        after_und = MagicMock(channel=channel, self_deaf=False, deaf=False)
        with patch("time.monotonic", return_value=9000.0):
            await self.cog.on_voice_state_update(member, before_und, after_und)
            self.assertIn((100, 1), self.cog._voice_cache)
            self.assertEqual(self.cog._voice_cache[(100, 1)], 9000.0)

    async def test_on_voice_state_update_switch_channels_same_guild(self):
        guild = MagicMock(id=100, afk_channel=None)
        channel1 = MagicMock(id=10, guild=guild)
        channel2 = MagicMock(id=20, guild=guild)
        member = MagicMock(bot=False, id=1, guild=guild)

        self.cog._voice_cache[(100, 1)] = 1000.0
        before = MagicMock(channel=channel1, self_deaf=False, deaf=False)
        after = MagicMock(channel=channel2, self_deaf=False, deaf=False)

        with patch("time.monotonic", return_value=2000.0):
            await self.cog.on_voice_state_update(member, before, after)
            self.mock_repo.add_balance.assert_not_called()
            self.assertEqual(self.cog._voice_cache[(100, 1)], 1000.0)

    async def test_on_voice_state_update_switch_to_afk_channel(self):
        afk_channel = MagicMock(id=999)
        guild = MagicMock(id=100, afk_channel=afk_channel)
        afk_channel.guild = guild
        normal_channel = MagicMock(id=10, guild=guild)
        member = MagicMock(bot=False, id=1, guild=guild)

        self.cog._voice_cache[(100, 1)] = 1000.0
        before = MagicMock(channel=normal_channel, self_deaf=False, deaf=False)
        after = MagicMock(channel=afk_channel, self_deaf=False, deaf=False)

        with patch("time.monotonic", return_value=4600.0):
            await self.cog.on_voice_state_update(member, before, after)
            self.assertNotIn((100, 1), self.cog._voice_cache)
            self.mock_repo.add_balance.assert_called_once_with(1, 100, 5)

    async def test_on_voice_state_update_leaves_cache_on_add_balance_failure(self):
        guild = MagicMock(id=100, afk_channel=None)
        channel = MagicMock(id=10, guild=guild)
        member = MagicMock(bot=False, id=1, guild=guild)

        self.cog._voice_cache[(100, 1)] = 1000.0
        self.mock_repo.add_balance = AsyncMock(side_effect=RuntimeError("Database failure"))

        before_leave = MagicMock(channel=channel, self_deaf=False, deaf=False)
        after_leave = MagicMock(channel=None, self_deaf=False, deaf=False)
        with patch("time.monotonic", return_value=4600.0):
            with self.assertRaises(RuntimeError):
                await self.cog.on_voice_state_update(member, before_leave, after_leave)

        self.assertIn((100, 1), self.cog._voice_cache)
        self.assertEqual(self.cog._voice_cache[(100, 1)], 1000.0)


class TestEconomyCogSlashCommands(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.logger_patcher = patch("extensions.economy.economy.CustomLogger")
        self.logger_patcher.start()
        self.mock_client = MagicMock()
        self.mock_client.boot_time = datetime.now()
        self.mock_repo = MagicMock(spec=EconomyRepository)
        self.cog = Economy(self.mock_client, economy_repo=self.mock_repo)
        for cmd in [
            self.cog.balance,
            self.cog.pay,
            self.cog.leaderboard,
            self.cog.give,
            self.cog.take,
            self.cog.set_balance,
        ]:
            cmd.cog = self.cog

    def tearDown(self):
        self.logger_patcher.stop()

    async def test_balance_caller(self):
        ctx = MagicMock()
        ctx.author = MagicMock(id=1, mention="<@1>")
        ctx.guild = MagicMock(id=100, emojis=[])
        ctx.response.send_message = AsyncMock()
        self.mock_repo.get_balance = AsyncMock(return_value=150)

        await self.cog.balance(ctx, member=None)
        self.mock_repo.get_balance.assert_called_once_with(1, 100)
        ctx.response.send_message.assert_called_once()
        self.assertTrue(ctx.response.send_message.call_args[1]["ephemeral"])
        embed = ctx.response.send_message.call_args[1]["embed"]
        self.assertIn("150 🐉 Dragon Scales", embed.description)

    async def test_balance_specified_member(self):
        ctx = MagicMock()
        ctx.author = MagicMock(id=1)
        ctx.guild = MagicMock(id=100, emojis=[])
        ctx.response.send_message = AsyncMock()
        target = MagicMock(id=2, mention="<@2>")
        self.mock_repo.get_balance = AsyncMock(return_value=1)

        await self.cog.balance(ctx, member=target)
        self.mock_repo.get_balance.assert_called_once_with(2, 100)
        self.assertTrue(ctx.response.send_message.call_args[1]["ephemeral"])
        embed = ctx.response.send_message.call_args[1]["embed"]
        self.assertIn("1 🐉 Dragon Scale", embed.description)

    async def test_balance_uses_app_emoji(self):
        self.mock_client.app_emojis = {"dragon_scale": "<:dragon_scale:555>"}
        ctx = MagicMock()
        ctx.author = MagicMock(id=1, mention="<@1>")
        ctx.guild = MagicMock(id=100, emojis=[])
        ctx.response.send_message = AsyncMock()
        self.mock_repo.get_balance = AsyncMock(return_value=150)

        await self.cog.balance(ctx, member=None)
        self.assertTrue(ctx.response.send_message.call_args[1]["ephemeral"])
        embed = ctx.response.send_message.call_args[1]["embed"]
        self.assertIn("150 <:dragon_scale:555> Dragon Scales", embed.description)

    async def test_pay_bot_fails(self):
        ctx = MagicMock()
        ctx.author = MagicMock(id=1)
        ctx.guild = MagicMock(id=100)
        ctx.response.send_message = AsyncMock()
        bot_target = MagicMock(bot=True, id=2)

        await self.cog.pay(ctx, member=bot_target, amount=50)
        ctx.response.send_message.assert_called_once_with("You cannot transfer Dragon Scales to a bot.", ephemeral=True)

    async def test_pay_self_fails(self):
        ctx = MagicMock()
        ctx.author = MagicMock(id=1)
        ctx.guild = MagicMock(id=100)
        ctx.response.send_message = AsyncMock()
        self_target = MagicMock(bot=False, id=1)

        await self.cog.pay(ctx, member=self_target, amount=50)
        ctx.response.send_message.assert_called_once_with(
            "You cannot transfer Dragon Scales to yourself.", ephemeral=True
        )

    async def test_pay_zero_or_negative_fails(self):
        ctx = MagicMock()
        ctx.author = MagicMock(id=1)
        ctx.guild = MagicMock(id=100)
        ctx.response.send_message = AsyncMock()
        target = MagicMock(bot=False, id=2)

        await self.cog.pay(ctx, member=target, amount=0)
        ctx.response.send_message.assert_called_once_with("The transfer amount must be greater than 0.", ephemeral=True)

    async def test_pay_insufficient_funds(self):
        ctx = MagicMock()
        ctx.author = MagicMock(id=1)
        ctx.guild = MagicMock(id=100, emojis=[])
        ctx.response.send_message = AsyncMock()
        target = MagicMock(bot=False, id=2)
        self.mock_repo.transfer_balance = AsyncMock(return_value=False)
        self.mock_repo.get_balance = AsyncMock(return_value=20)

        await self.cog.pay(ctx, member=target, amount=50)
        self.mock_repo.transfer_balance.assert_called_once_with(1, 2, 100, 50)
        ctx.response.send_message.assert_called_once()
        self.assertTrue(ctx.response.send_message.call_args[1]["ephemeral"])

    async def test_pay_success(self):
        ctx = MagicMock()
        ctx.author = MagicMock(id=1)
        ctx.guild = MagicMock(id=100, emojis=[])
        ctx.response.send_message = AsyncMock()
        target = MagicMock(bot=False, id=2, mention="<@2>")
        self.mock_repo.transfer_balance = AsyncMock(return_value=True)

        await self.cog.pay(ctx, member=target, amount=50)
        self.mock_repo.transfer_balance.assert_called_once_with(1, 2, 100, 50)
        ctx.response.send_message.assert_called_once_with("Successfully transferred 50 🐉 Dragon Scales to <@2>!")

    async def test_leaderboard_empty(self):
        ctx = MagicMock()
        ctx.guild = MagicMock(id=100, emojis=[])
        ctx.response.send_message = AsyncMock()
        self.mock_repo.get_leaderboard = AsyncMock(return_value=[])

        await self.cog.leaderboard(ctx)
        ctx.response.send_message.assert_called_once_with("No members have any Dragon Scales yet.", ephemeral=True)

    async def test_leaderboard_populated(self):
        ctx = MagicMock()
        ctx.guild = MagicMock(id=100, emojis=[])
        ctx.response.send_message = AsyncMock()
        w1 = SimpleNamespace(user_id=1, balance=500)
        w2 = SimpleNamespace(user_id=2, balance=250)
        self.mock_repo.get_leaderboard = AsyncMock(return_value=[w1, w2])

        await self.cog.leaderboard(ctx)
        ctx.response.send_message.assert_called_once()
        self.assertTrue(ctx.response.send_message.call_args[1]["ephemeral"])
        embed = ctx.response.send_message.call_args[1]["embed"]
        self.assertIn("**#1** <@1> — 500 🐉 Dragon Scales", embed.description)
        self.assertIn("**#2** <@2> — 250 🐉 Dragon Scales", embed.description)

    async def test_give_command(self):
        ctx = MagicMock()
        ctx.guild = MagicMock(id=100, emojis=[])
        ctx.response.send_message = AsyncMock()
        target = MagicMock(id=2, mention="<@2>")
        self.mock_repo.add_balance = AsyncMock(return_value=300)

        # Invalid amount
        await self.cog.give(ctx, member=target, amount=0)
        ctx.response.send_message.assert_called_with("The amount must be greater than 0.", ephemeral=True)

        # Valid amount
        await self.cog.give(ctx, member=target, amount=100)
        self.mock_repo.add_balance.assert_called_once_with(2, 100, 100)
        self.assertIn("Added 100 🐉 Dragon Scales to <@2>", ctx.response.send_message.call_args[0][0])
        self.assertTrue(ctx.response.send_message.call_args[1]["ephemeral"])

    async def test_take_command(self):
        ctx = MagicMock()
        ctx.guild = MagicMock(id=100, emojis=[])
        ctx.response.send_message = AsyncMock()
        target = MagicMock(id=2, mention="<@2>")

        # Invalid amount
        await self.cog.take(ctx, member=target, amount=0)
        ctx.response.send_message.assert_called_with("The amount must be greater than 0.", ephemeral=True)

        # Insufficient funds
        self.mock_repo.remove_balance = AsyncMock(return_value=False)
        self.mock_repo.get_balance = AsyncMock(return_value=20)
        await self.cog.take(ctx, member=target, amount=50)
        self.assertIn("Cannot take 50 🐉 Dragon Scales from <@2>", ctx.response.send_message.call_args[0][0])
        self.assertTrue(ctx.response.send_message.call_args[1]["ephemeral"])

        # Success
        self.mock_repo.remove_balance = AsyncMock(return_value=True)
        self.mock_repo.get_balance = AsyncMock(return_value=50)
        await self.cog.take(ctx, member=target, amount=50)
        self.assertIn("Took 50 🐉 Dragon Scales from <@2>", ctx.response.send_message.call_args[0][0])
        self.assertTrue(ctx.response.send_message.call_args[1]["ephemeral"])

    async def test_set_balance_command(self):
        ctx = MagicMock()
        ctx.guild = MagicMock(id=100, emojis=[])
        ctx.response.send_message = AsyncMock()
        target = MagicMock(id=2, mention="<@2>")

        # Negative
        await self.cog.set_balance(ctx, member=target, amount=-10)
        ctx.response.send_message.assert_called_with("The amount cannot be negative.", ephemeral=True)

        # Valid
        self.mock_repo.set_balance = AsyncMock(return_value=400)
        await self.cog.set_balance(ctx, member=target, amount=400)
        self.mock_repo.set_balance.assert_called_once_with(2, 100, 400)
        self.assertIn("Set balance of <@2> to 400 🐉 Dragon Scales.", ctx.response.send_message.call_args[0][0])
        self.assertTrue(ctx.response.send_message.call_args[1]["ephemeral"])
