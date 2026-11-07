from collections.abc import Sequence
import io
import uuid as _uuid

import discord
from discord.ext import commands
from discord.utils import escape_markdown, get_or_fetch

from utils import Bot, ButtonConfirm, CustomLogger, SettingsEnum

from .channel_exporter import export_and_archive_channel
from .models import Modmail
from .repository import ModmailRepository

__all__ = [
    "CloseModmailThreadView",
    "EndModmailView",
    "GuildSelectDropdown",
    "GuildSelectView",
    "ModMail",
    "close_and_archive_modmail",
    "setup",
]


def _first_int(uuid: str) -> int:
    """
    Converts a UUID to an integer which is less than or equal to 5.

    Args:
        uuid: A UUID string.

    Returns:
        An integer between 0 and 5.
    """
    for x in uuid:
        if x.isdigit():
            num = int(x)
            return num // 2 if num > 5 else num
    return 0


def _to_embed(msg: discord.Message, uuid: str, anonymous: bool) -> discord.Embed:
    """
    Converts a discord.Message to a discord.Embed.
    If anonymous is True, user identity is completely hidden.
    """
    if anonymous:
        num = _first_int(uuid)
        icon_url = f"https://cdn.discordapp.com/embed/avatars/{num}.png"
        author = discord.EmbedAuthor(name=f"Anon#{uuid[:7]}", icon_url=icon_url)
        footer = discord.EmbedFooter(text=f"UUID: {uuid}")
    else:
        author = discord.EmbedAuthor(
            name=msg.author.name,
            url=f"https://discord.id/?prefill={msg.author.id}",
            icon_url=msg.author.display_avatar.url,
        )
        footer = discord.EmbedFooter(text=f"Member ID: {msg.author.id}")

    return discord.Embed(
        author=author,
        color=discord.Color.dark_magenta(),
        description=msg.content,
        footer=footer,
        timestamp=msg.created_at,
    )


def _modmail_thread_name(mail: Modmail, user_name: str | None = None) -> str:
    """Returns the expected thread name for a modmail session."""
    if mail.anon:
        return f"Thread for Anon#{mail.uuid[:7]}"
    name = user_name or "Unknown"
    return f"Thread for {escape_markdown(name)}"


async def _get_thread_by_id(
    bot: Bot,
    guild: discord.Guild,
    modmail_channel: discord.TextChannel | None,
    thread_id: int | None,
) -> discord.Thread | None:
    """Fetches or resolves a thread by its thread_id."""
    if thread_id is None:
        return None
    thread = guild.get_thread(thread_id)
    if thread is not None:
        return thread
    thread = await get_or_fetch(bot, "channel", thread_id, default=None)
    if thread is not None:
        return thread
    if modmail_channel is not None and hasattr(modmail_channel, "threads"):
        return discord.utils.get(modmail_channel.threads, id=thread_id)
    return None


def _find_thread_by_name(
    modmail_channel: discord.TextChannel | None,
    target_name: str | None,
) -> discord.Thread | None:
    """Searches active unarchived/unlocked threads in modmail channel by name."""
    if modmail_channel is None or target_name is None or not hasattr(modmail_channel, "threads"):
        return None
    for th in modmail_channel.threads:
        if th.name == target_name and not th.archived and not th.locked:
            return th
    return None


async def _resolve_modmail_thread(
    bot: Bot,
    mail: Modmail,
    guild: discord.Guild,
    modmail_channel: discord.TextChannel | None,
) -> discord.Thread | None:
    """Finds the Discord thread for an active modmail session by thread_id or name fallback."""
    thread = await _get_thread_by_id(bot, guild, modmail_channel, mail.thread_id)
    if thread is not None:
        return thread

    user_name = None
    if not mail.anon:
        user = await get_or_fetch(bot, "user", mail.user_id, default=None)
        user_name = user.name if user else None

    target_name = _modmail_thread_name(mail, user_name)
    return _find_thread_by_name(modmail_channel, target_name)


def _closure_message(mail: Modmail, closer: discord.User | discord.Member, closed_by_staff: bool) -> str:
    """Formats the closure announcement message preserving anonymity if anon is True."""
    if closed_by_staff:
        return f"{escape_markdown(closer.name)} has closed the conversation!"
    closer_name = f"Anon#{mail.uuid[:7]}" if mail.anon else escape_markdown(closer.name)
    return f"{closer_name} has closed the conversation!"


async def _send_closure_transcript(
    modmail_channel: discord.TextChannel | None,
    thread_name: str,
    transcript_html: str | None,
    archive_id: int | None,
) -> None:
    """Posts exported HTML transcript file to modmail_channel if present."""
    if not transcript_html or modmail_channel is None:
        return
    filename = f"{thread_name}.html"
    file = discord.File(fp=io.StringIO(transcript_html), filename=filename)
    summary_msg = f"Modmail transcript for **{thread_name}** (Archive ID: `{archive_id}`)"
    try:
        await modmail_channel.send(content=summary_msg, file=file)
    except Exception:
        pass


async def _notify_user_closure(bot: Bot, guild_name: str, user_id: int) -> None:
    """Sends a closure notification DM to the user when staff closes modmail."""
    user = await get_or_fetch(bot, "user", user_id, default=None)
    if user is None:
        return
    try:
        await user.send(f"Your modmail with **{escape_markdown(guild_name)}** has been closed by staff.")
    except Exception:
        pass


async def _has_team_role(bot: Bot, guild: discord.Guild, member: discord.Member) -> bool:
    if not hasattr(bot, "db") or not hasattr(bot.db, "get_setting"):
        return False
    try:
        setting = await bot.db.get_setting(SettingsEnum.TeamRole, guild)
        if setting is None:
            return False
        team_role_id = setting[0].value if isinstance(setting, (tuple, list, Sequence)) else setting.value
        return any(getattr(r, "id", None) == team_role_id for r in getattr(member, "roles", []))
    except Exception:
        return False


async def _can_close_modmail(
    bot: Bot,
    mail: Modmail,
    user: discord.User | discord.Member,
    guild: discord.Guild | None,
) -> bool:
    """Checks whether the user has permission to close the modmail session."""
    if user.id == mail.user_id:
        return True

    if guild is None:
        return False

    member: discord.Member | None = user if isinstance(user, discord.Member) else None
    if member is None and hasattr(guild, "get_member"):
        member = guild.get_member(user.id)
    if member is None and hasattr(guild, "get_or_fetch"):
        try:
            member = await get_or_fetch(guild, "member", user.id, default=None)
        except Exception:
            pass

    if member is None:
        return False

    perms = getattr(member, "guild_permissions", None)
    if getattr(perms, "administrator", False):
        return True

    return await _has_team_role(bot, guild, member)


async def close_and_archive_modmail(
    bot: Bot,
    mail: Modmail,
    closer: discord.User | discord.Member,
    modmail_repo: ModmailRepository,
    closed_by_staff: bool = False,
) -> None:
    """
    Notifies thread, archives and exports HTML transcript, sends transcript file
    to modmail_channel, locks & archives thread, and deletes the Modmail DB record.
    """
    guild = bot.get_guild(mail.guild_id)
    if guild is None:
        guild = await get_or_fetch(bot, "guild", mail.guild_id, default=None)
    if guild is None:
        await modmail_repo.delete_modmail(uuid=mail.uuid)
        return

    modmail_channel = None
    try:
        setting = await bot.db.get_setting(SettingsEnum.ModmailChannel, guild)
        if setting is not None:
            modmail_channel = await get_or_fetch(guild, "channel", setting.value, default=None)
    except Exception:
        pass

    thread = await _resolve_modmail_thread(bot, mail, guild, modmail_channel)
    if thread is not None:
        close_msg = _closure_message(mail, closer, closed_by_staff)
        try:
            await thread.send(close_msg)
        except Exception:
            pass

        transcript_html, archive_id = await export_and_archive_channel(
            bot=bot,
            channel=thread,
            guild=guild,
            exported_by_id=closer.id,
        )
        await _send_closure_transcript(modmail_channel, thread.name, transcript_html, archive_id)
        try:
            await thread.edit(locked=True, archived=True)
        except Exception:
            pass

    await modmail_repo.delete_modmail(uuid=mail.uuid)

    if closed_by_staff:
        await _notify_user_closure(bot, guild.name, mail.user_id)


class CloseModmailThreadView(discord.ui.View):
    """Persistent view placed in the thread starter message for staff to close and archive."""

    def __init__(self, bot: Bot | None = None, modmail_repo: ModmailRepository | None = None):
        super().__init__(timeout=None)
        self.bot = bot
        self.modmail_repo = modmail_repo

    @discord.ui.button(
        label="Close & Archive Modmail",
        style=discord.ButtonStyle.danger,
        custom_id="modmail__close_thread_button",
    )
    async def close_thread_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        bot = self.bot or getattr(interaction.client, "bot", interaction.client)
        modmail_repo = self.modmail_repo or ModmailRepository(bot.db.session_maker)

        mail = await modmail_repo.get_modmail(thread_id=interaction.channel_id)
        if mail is None:
            return await interaction.response.send_message(
                "This modmail is already closed or could not be found.", ephemeral=True
            )

        guild = interaction.guild or bot.get_guild(mail.guild_id)
        if not await _can_close_modmail(bot, mail, interaction.user, guild):
            return await interaction.response.send_message(
                "You do not have permission to close this Modmail ticket.", ephemeral=True
            )

        await interaction.response.send_message("Closing and archiving modmail thread...", ephemeral=True)
        await close_and_archive_modmail(
            bot=bot,
            mail=mail,
            closer=interaction.user,
            modmail_repo=modmail_repo,
            closed_by_staff=True,
        )


class EndModmailView(discord.ui.View):
    def __init__(self, author: discord.User, client: Bot, modmail_repo: ModmailRepository | None = None):
        super().__init__(timeout=30, disable_on_timeout=True)
        self.author = author
        self.client = client
        self.modmail_repo = modmail_repo or ModmailRepository(client.db.session_maker)

    @discord.ui.button(
        label="End Modmail",
        style=discord.ButtonStyle.blurple,
    )
    async def end_modmail(self, button: discord.ui.Button, interaction: discord.Interaction):
        mail = await self.modmail_repo.get_modmail(user=self.author)
        if mail is None:
            return await interaction.response.send_message("You are not chatting with any guild!", ephemeral=True)

        guild = self.client.get_guild(mail.guild_id)
        if guild is None:
            guild = await get_or_fetch(self.client, "guild", mail.guild_id, default=None)
        guild_name = guild.name if guild else "the guild"

        button.label = "Stopped Modmailing"
        button.disabled = True
        button.style = discord.ButtonStyle.success
        await interaction.edit(
            content=f"You've stopped mailing with **{escape_markdown(guild_name)}**!",
            view=self,
        )

        await close_and_archive_modmail(
            bot=self.client,
            mail=mail,
            closer=self.author,
            modmail_repo=self.modmail_repo,
            closed_by_staff=False,
        )


class GuildSelectDropdown(discord.ui.Select):
    def __init__(
        self, client_: Bot, author: discord.User, anonymous: bool, modmail_repo: ModmailRepository | None = None
    ):
        self.client = client_
        self.modmail_repo = modmail_repo or ModmailRepository(client_.db.session_maker)
        self.author = author
        self.anon = anonymous
        options = [discord.SelectOption(label=guild.name, value=str(guild.id)) for guild in author.mutual_guilds]
        super().__init__(
            placeholder="Choose the guild to modmail with!",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        response = int(self.values[0])
        mail = await self.modmail_repo.get_modmail(user=self.author)
        if mail:
            response = mail.guild_id
        guild = self.client.get_guild(response)
        if guild is None:
            guild = await get_or_fetch(self.client, "guild", response, default=None)
        if guild and mail and mail.guild_id == guild.id:
            view = EndModmailView(self.author, self.client, self.modmail_repo)
            await interaction.response.send_message(
                f"You are still chatting with **{escape_markdown(guild.name)}**", view=view
            )
        elif guild:
            uuid = str(_uuid.uuid4())
            await self.modmail_repo.create_modmail(self.author, guild, uuid, self.anon)
            await interaction.response.send_message(
                f"You are now chatting with **{escape_markdown(guild.name)}**!", ephemeral=True
            )


class GuildSelectView(discord.ui.View):
    def __init__(
        self, client: Bot, author: discord.User, anonymous: bool, modmail_repo: ModmailRepository | None = None
    ):
        super().__init__(timeout=30, disable_on_timeout=True)
        self.add_item(GuildSelectDropdown(client, author, anonymous, modmail_repo))


class ModMail(commands.Cog):
    def __init__(self, client: Bot, modmail_repo: ModmailRepository | None = None):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)
        self.modmail_repo = modmail_repo or ModmailRepository(self.client.db.session_maker)

    @commands.Cog.listener("on_ready", once=True)
    async def on_ready(self):
        self.client.add_view(CloseModmailThreadView(self.client, self.modmail_repo))

    modmail_group = discord.SlashCommandGroup(
        "modmail",
        contexts={
            discord.InteractionContextType.guild,
            discord.InteractionContextType.bot_dm,
            discord.InteractionContextType.private_channel,
        },
    )

    @modmail_group.command(name="create", description="Start a new modmail chat.")
    @discord.commands.option(
        name="anonymous", description="Do you want to be anonymous in this modmail?", input_type=bool, default=False
    )
    async def create_modmail(self, ctx: discord.ApplicationContext, anonymous: bool):
        mail = await self.modmail_repo.get_modmail(user=ctx.author)
        if mail:
            guild: discord.Guild = await get_or_fetch(self.client, "guild", mail.guild_id, default=None)
            guild_name = guild.name if guild else str(mail.guild_id)
            view = EndModmailView(ctx.author, self.client, self.modmail_repo)
            msg = (
                "You are still chatting with this guild!"
                if ctx.guild and ctx.guild.id == mail.guild_id
                else f"You are still chatting with **{escape_markdown(guild_name)}**!"
            )
            return await ctx.response.send_message(msg, view=view, ephemeral=True)

        if ctx.guild:
            uuid = str(_uuid.uuid4())
            await self.modmail_repo.create_modmail(ctx.author, ctx.guild, uuid, anonymous)
            return await ctx.response.send_message(
                "A new modmail will be created. Please check your DM's", ephemeral=True
            )

        view = GuildSelectView(self.client, ctx.author, anonymous, self.modmail_repo)
        return await ctx.response.send_message("With which guild do you want to modmail?", ephemeral=True, view=view)

    @modmail_group.command(name="end", description="Stop a modmail chat.")
    async def end_modmail(self, ctx: discord.ApplicationContext):
        mail = await self.modmail_repo.get_modmail(user=ctx.author)
        if mail is None or mail.user_id is None:
            return await ctx.response.send_message("You are not chatting with any guild!", ephemeral=True)

        guild: discord.Guild = await get_or_fetch(self.client, "guild", mail.guild_id, default=None)
        guild_name = guild.name if guild else "the guild"
        view = ButtonConfirm(cancel_title=f"You continue to mail with **{escape_markdown(guild_name)}**!")
        msg = await ctx.response.send_message(
            f"Do you really want to stop mailing with **{escape_markdown(guild_name)}**?", view=view, ephemeral=True
        )
        view.original_msg = msg
        await view.wait()
        if view.value is None or not view.value:
            return

        await close_and_archive_modmail(
            bot=self.client,
            mail=mail,
            closer=ctx.author,
            modmail_repo=self.modmail_repo,
            closed_by_staff=False,
        )
        await ctx.followup.send(
            f"You've stopped mailing with **{escape_markdown(guild_name)}**!",
            ephemeral=True,
        )

    @modmail_group.command(name="close", description="Close and archive a modmail thread.")
    async def close_modmail(self, ctx: discord.ApplicationContext):
        mail = None
        closed_by_staff = False

        if ctx.guild:
            mail = await self.modmail_repo.get_modmail(thread_id=ctx.channel.id)
            if mail is not None:
                closed_by_staff = ctx.author.id != mail.user_id
        else:
            mail = await self.modmail_repo.get_modmail(user=ctx.author)

        if mail is None:
            return await ctx.response.send_message(
                "No active modmail session or thread found to close!", ephemeral=True
            )

        if not await _can_close_modmail(self.client, mail, ctx.author, ctx.guild):
            return await ctx.response.send_message(
                "You do not have permission to close this Modmail ticket.", ephemeral=True
            )

        await ctx.response.send_message("Closing and archiving modmail...", ephemeral=True)
        await close_and_archive_modmail(
            bot=self.client,
            mail=mail,
            closer=ctx.author,
            modmail_repo=self.modmail_repo,
            closed_by_staff=closed_by_staff,
        )

    async def _find_mail_fallback(self, thread: discord.Thread) -> Modmail | None:
        if not hasattr(thread, "history"):
            return None
        async for message in thread.history(limit=50):
            if not message.embeds or not message.embeds[0].footer or not message.embeds[0].footer.text:
                continue
            footer = message.embeds[0].footer.text
            mail = None
            if footer.startswith("UUID: "):
                mail = await self.modmail_repo.get_modmail(uuid=footer.removeprefix("UUID: ").strip())
            elif footer.startswith("Member ID: "):
                user_id_str = footer.removeprefix("Member ID: ").strip()
                if user_id_str.isdigit():
                    mail = await self.modmail_repo.get_modmail(user=discord.Object(id=int(user_id_str)))
            if mail is not None:
                await self.modmail_repo.update_thread_id(mail.uuid, thread.id)
                mail.thread_id = thread.id
                return mail
        return None

    async def _handle_guild_message(self, msg: discord.Message) -> None:
        if not isinstance(msg.channel, discord.Thread) and getattr(msg.channel, "type", None) not in (
            discord.ChannelType.public_thread,
            discord.ChannelType.private_thread,
        ):
            return

        setting = await self.client.db.get_setting(SettingsEnum.ModmailChannel, msg.guild)
        if setting is None:
            return

        parent_id = getattr(msg.channel, "parent_id", None)
        if parent_id is None and getattr(msg.channel, "parent", None) is not None:
            parent_id = msg.channel.parent.id
        if parent_id is not None and parent_id != setting.value:
            return

        mail = await self.modmail_repo.get_modmail(thread_id=msg.channel.id)
        if mail is None:
            mail = await self._find_mail_fallback(msg.channel)
        if mail is None:
            return

        user = await get_or_fetch(self.client, "user", mail.user_id, default=None)
        if user is None:
            await msg.reply("User could not be found!\nMaybe they've deleted their account.")
            return

        files = [await att.to_file() for att in msg.attachments]
        embed = discord.Embed(
            author=discord.EmbedAuthor(name=msg.author.name, icon_url=msg.author.display_avatar.url),
            color=discord.Color.dark_magenta(),
            description=msg.content,
            footer=discord.EmbedFooter(text=f"Member ID: {msg.author.id}"),
            timestamp=msg.created_at,
        )
        await user.send(embed=embed, files=files or None)

    async def _get_or_create_thread(
        self,
        mail: Modmail,
        guild: discord.Guild,
        modmail_channel: discord.TextChannel,
        author: discord.User | discord.Member,
    ) -> tuple[discord.Thread, bool]:
        thread = await _get_thread_by_id(self.client, guild, modmail_channel, mail.thread_id)
        if thread is not None and not thread.archived and not thread.locked:
            return thread, False

        target_name = _modmail_thread_name(mail, author.name)
        existing = _find_thread_by_name(modmail_channel, target_name)
        if existing is not None:
            await self.modmail_repo.update_thread_id(mail.uuid, existing.id)
            mail.thread_id = existing.id
            return existing, False

        start_msg = await modmail_channel.send(f"Creating {target_name}")
        new_thread = await start_msg.create_thread(name=target_name, auto_archive_duration=4320)
        await self.modmail_repo.update_thread_id(mail.uuid, new_thread.id)
        mail.thread_id = new_thread.id
        return new_thread, True

    async def _handle_dm_message(self, msg: discord.Message) -> None:
        mail = await self.modmail_repo.get_modmail(user=msg.author)
        if mail is None:
            await msg.author.send(f"If you want to modmail with someone please use first {self.create_modmail.mention}")
            return

        guild = await get_or_fetch(self.client, "guild", mail.guild_id, default=None)
        if guild is None:
            return

        for attachment in msg.attachments:
            if attachment.size is not None and attachment.size >= 10000000:
                await msg.channel.send(
                    f"## Error\nYour file ({escape_markdown(attachment.filename)}) is to large to be send!\n"
                    "Maximum to be sent are 10MB"
                )
                return

        try:
            modmail_setting = await self.client.db.get_setting(SettingsEnum.ModmailChannel, guild)
        except AttributeError:
            modmail_setting = None

        if not modmail_setting:
            await msg.author.send(
                "This feature is not set up in the guild you are trying to chat with.\n"
                "-# You'll have to contact the mods or owner directly and let them enable this feature for you!",
                delete_after=20,
            )
            return

        modmail_channel: discord.TextChannel = await get_or_fetch(guild, "channel", modmail_setting.value, default=None)
        if modmail_channel is None:
            if guild.owner:
                await guild.owner.send("Your modmail setting is outdated, please update it!")
            return

        thread, is_new = await self._get_or_create_thread(mail, guild, modmail_channel, msg.author)
        files = [await att.to_file() for att in msg.attachments]
        embed = _to_embed(msg, mail.uuid, mail.anon)
        if is_new:
            await thread.send(
                embed=embed,
                files=files or None,
                view=CloseModmailThreadView(self.client, self.modmail_repo),
            )
        else:
            await thread.send(embed=embed, files=files or None)

    @commands.Cog.listener("on_message")
    async def on_modmail(self, msg: discord.Message):
        if msg.author.bot:
            return
        if msg.guild:
            await self._handle_guild_message(msg)
        else:
            await self._handle_dm_message(msg)


def setup(client: Bot):
    client.add_cog(ModMail(client))
