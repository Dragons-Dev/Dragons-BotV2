import discord
from discord.ext import commands, tasks
from datetime import datetime
from config import SERVER_TZ
from enum import Enum
from utils import Event
from utils import Bot, CustomLogger
import pycord.multicog as pycog


async def event_choices(ctx: discord.AutocompleteContext) -> list[str]:
    """Supplies all event ids owned by the ctx.interaction.user

    Args:
        ctx (discord.AutocompleteContext):

    Returns:
        list[str]: all event ids owned by the ctx.interaction.user
    """
    bot: Bot = ctx.bot
    now = datetime.now(tz=SERVER_TZ)
    events = await bot.db.get_events()
    filtered_events = []
    for event in events:
        event_time = event.time.replace(tzinfo=SERVER_TZ)
        if event.host == ctx.interaction.user.id and event_time >= now:
            filtered_events.append(f"{event.name} | {event.time.strftime('%H:%M %d.%m.%Y')}")
    return filtered_events


REMINDER_BUTTONS = {
    "1 Min": 60,
    "10 Min": 600,
    "1 Std": 3600,
    "1 Tag": 86400,
}


class InviteMode(Enum):
    OPEN = "OPEN"
    INVITE_ONLY = "INVITE_ONLY"
    CLOSED = "CLOSED"


class ParticipationView(discord.ui.View):
    def __init__(self, client: Bot, event_id: str):
        super().__init__(timeout=None)
        self.client = client
        self.event_id = event_id

    async def _respond(self, interaction: discord.Interaction, status: bool):
        status_update = await self.client.db.update_confirmation(
            event_id=self.event_id, guest=interaction.user.id, confirmation=status
        )
        if status_update:
            await interaction.response.send_message(
                f"✅ Your answer **{'Accept' if status else 'Reject'}** was stored."
            )
        else:
            await interaction.response.send_message(
                "Something went wrong.",
            )

    @discord.ui.button(label="✅ Accept", style=discord.ButtonStyle.success)
    async def accept(self, button, interaction: discord.Interaction):
        await self._respond(interaction, True)

    @discord.ui.button(label="❌ Reject", style=discord.ButtonStyle.danger)
    async def decline(self, button, interaction: discord.Interaction):
        await self._respond(interaction, False)


class InviteRequestView(discord.ui.View):
    def __init__(self, client: Bot, event_id: str, requester: discord.User):
        super().__init__(timeout=None)
        self.client = client
        self.event_id = event_id
        self.requester = requester

    async def _respond(self, interaction: discord.Interaction, status: bool):
        if status:
            already_invites = await self.client.db.get_all_confirmations_for_event(event_id=self.event_id)
            if self.requester.id not in already_invites:
                await self.client.db.create_confirmation(
                    event_id=self.event_id, guest=self.requester.id, confirmation=None
                )
            event_obj: Event = await self.client.db.get_event_by_id(id=self.event_id)
            em = discord.Embed(title="⏰ **Event**", color=discord.Color.brand_green())
            em.add_field(
                name="",
                value=f"📅 **You were invited to {event_obj.name}!** \n on {event_obj.time.date()} at 🕒{event_obj.time.time().strftime('%H:%M')}.",
            )
            em.set_footer(text="Please confirm your participation 👇.")
            await self.requester.send(embed=em, view=ParticipationView(self.client, self.event_id))
            await interaction.response.send_message("✅ Invitation was send.")

        else:
            await interaction.response.send_message("Something went wrong.")

    @discord.ui.button(label="✅ Accept", style=discord.ButtonStyle.success)
    async def accept(self, button, interaction: discord.Interaction):
        await self._respond(interaction, True)

    @discord.ui.button(label="❌ Reject", style=discord.ButtonStyle.danger)
    async def decline(self, button, interaction: discord.Interaction):
        await self._respond(interaction, False)


class EventRequestInviteModal(discord.ui.DesignerModal):
    def __init__(self, ctx: discord.ApplicationContext, client: Bot, events: list[Event], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = client
        options = []
        self.events = events
        for event in self.events:
            option = discord.SelectOption(
                label=f"{event.name} | {event.time.strftime('%H:%M %d.%m.%Y')}", value=event.id
            )
            options.append(option)

        if options == []:
            options = None
        self.event = discord.ui.Label(
            "Event",
            discord.ui.Select(
                placeholder="Select the Event you want to attend.",
                required=True,
                options=options,
                min_values=1,
                max_values=1,
            ),
        )
        self.add_item(self.event)

    async def callback(self, interaction):
        event_id = self.event.item.values[0]
        event_obj = await self.client.db.get_event_by_id(id=event_id)
        try:
            already_invites = await self.client.db.get_all_confirmations_for_event(event_id=event_id)

            if (
                event_obj.mode == InviteMode.OPEN.value
                or (event_obj.mode == InviteMode.INVITE_ONLY.value and interaction.user.id in already_invites)
                or (event_obj.mode == InviteMode.CLOSED.value and interaction.user.id in already_invites)
            ):
                if interaction.user.id not in already_invites:
                    await self.client.db.create_confirmation(
                        event_id=event_id, guest=interaction.user.id, confirmation=None
                    )
                em = discord.Embed(title="⏰ **Event**", color=discord.Color.brand_green())
                em.add_field(
                    name="",
                    value=f"📅 **You were invited to {event_obj.name}!** \n on {event_obj.time.date()} at 🕒{event_obj.time.time().strftime('%H:%M')}.",
                )
                em.set_footer(text="Please confirm your participation 👇.")
                await interaction.user.send(embed=em, view=ParticipationView(self.client, event_id))
                await interaction.respond(
                    f"{interaction.user} was invited to the event.",
                    ephemeral=True,
                    delete_after=5,
                )
            elif event_obj.mode == InviteMode.INVITE_ONLY.value:
                # Sends the host a message and ask them if they want to invite the user.

                host = await self.client.get_or_fetch_user(event_obj.host)
                em = discord.Embed(title="⏰ **Event**", color=discord.Color.brand_green())
                em.add_field(
                    name="",
                    value=f"📅 **{interaction.user} wants to attend {event_obj.name}!** \n on {event_obj.time.date()} at 🕒{event_obj.time.time().strftime('%H:%M')}.",
                )
                em.set_footer(text="Please accept or deny 👇.")
                await host.send(embed=em, view=InviteRequestView(self.client, event_id, interaction.user))
                await interaction.respond(
                    f"{host} was asked if you can attend.",
                    ephemeral=True,
                    delete_after=5,
                )

        except discord.Forbidden:
            await interaction.respond(
                f"{interaction.user} was not invited to the event, because the user not allows direct messages.",
                ephemeral=True,
                delete_after=5,
            )
            pass  # DMs geschlossen


class EventInviteModal(discord.ui.DesignerModal):
    def __init__(self, ctx: discord.ApplicationContext, client: Bot, events: list[Event], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = client
        options = []
        self.events = events
        for event in self.events:
            if ctx.interaction.user.id == event.host:
                option = discord.SelectOption(
                    label=f"{event.name} | {event.time.strftime('%H:%M %d.%m.%Y')}", value=event.id
                )
                options.append(option)

        if options == []:
            options = None

        self.event = discord.ui.Label(
            "Event",
            discord.ui.Select(
                placeholder="Select the Event you want invite to.",
                required=True,
                options=options,
                min_values=1,
                max_values=1,
            ),
        )
        self.invites = discord.ui.Label(
            "Invites",
            discord.ui.Select(
                select_type=discord.ComponentType.user_select,
                placeholder="Select all you want to invite.",
                required=True,
                max_values=25,
            ),
        )
        self.add_item(self.event)
        self.add_item(self.invites)

    async def callback(self, interaction):
        event_id = self.event.item.values[0]
        event_obj: Event = await self.client.db.get_event_by_id(id=event_id)
        invites = self.invites.item.values
        try:
            for invite in invites:
                already_invites = await self.client.db.get_all_confirmations_for_event(event_id=event_id)
                if invite.id not in already_invites:
                    await self.client.db.create_confirmation(event_id=event_id, guest=invite.id, confirmation=None)

                em = discord.Embed(title="⏰ **Event**", color=discord.Color.brand_green())
                em.add_field(
                    name="",
                    value=f"📅 **You were invited to {event_obj.name}!** \n on {event_obj.time.date()} at 🕒{event_obj.time.time().strftime('%H:%M')}.",
                )
                em.set_footer(text="Please confirm your participation 👇.")
                await invite.send(embed=em, view=ParticipationView(self.client, event_id))
                await interaction.respond(
                    f"{invite} was invited to the event.",
                    ephemeral=True,
                    delete_after=5,
                )
        except discord.Forbidden:
            await interaction.respond(
                f"{invite} was not invited to the event, because the user not allows direct messages.",
                ephemeral=True,
                delete_after=5,
            )
            pass


class EventReminderModal(discord.ui.DesignerModal):
    def __init__(self, guild: discord.Guild, client: Bot, host: discord.User, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.guild = guild
        self.client = client
        self.host = host

        self.event_name = discord.ui.Label(
            "The name of the event.",
            discord.ui.InputText(
                placeholder="e.g. Game Night",
                required=True,
            ),
        )

        self.event_time = discord.ui.Label(
            "When will the event happen:",
            discord.ui.InputText(
                placeholder="TT.MM.JJJJ HH:MM",
                required=True,
            ),
        )

        self.event_guests = discord.ui.Label(
            "Guests",
            discord.ui.Select(
                select_type=discord.ComponentType.user_select,
                placeholder="Select all you want to invite.",
                required=True,
                max_values=25,
            ),
        )

        options = []
        for reminder in REMINDER_BUTTONS:
            d_option = discord.SelectOption(label=reminder, value=str(REMINDER_BUTTONS[reminder]))
            options.append(d_option)
        self.event_reminders = discord.ui.Label(
            "Select",
            discord.ui.Select(
                placeholder="Select a reminder.",
                options=options,
                required=True,
                max_values=len(options),
            ),
        )

        options = []
        for mode in InviteMode:
            d_option = discord.SelectOption(label=mode.name, value=mode.value)
            options.append(d_option)
        self.event_mode = discord.ui.Label(
            "Invite Mode", discord.ui.Select(placeholder="Select an invite mode.", options=options, required=True)
        )

        self.add_item(self.event_name)
        self.add_item(self.event_time)
        self.add_item(self.event_guests)
        self.add_item(self.event_reminders)
        self.add_item(self.event_mode)

    async def callback(self, interaction: discord.Interaction):
        try:
            event_time_local = datetime.strptime(self.event_time.item.value.strip(), "%d.%m.%Y %H:%M")
            event_time_local = event_time_local.replace(tzinfo=SERVER_TZ)
            now = datetime.now(tz=SERVER_TZ)
            if event_time_local < now:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                "Invalid date.\nPlease use: TT.MM.JJJJ HH:MM\nExample: 10.02.2026 18:00\nAnd event needs to be in the future.",
                ephemeral=True,
                delete_after=5,
            )
            return
        guests = []
        for guest in self.event_guests.item.values:
            guests.append(guest)
        reminders = list(map(int, self.event_reminders.item.values))

        if self.event_mode.item.values[0] == InviteMode.OPEN.value:
            mode = InviteMode.OPEN.value
        elif self.event_mode.item.values[0] == InviteMode.INVITE_ONLY.value:
            mode = InviteMode.INVITE_ONLY.value
        else:
            mode = InviteMode.CLOSED.value

        event_id = await self.client.db.create_event(
            host=self.host.id,
            name=self.event_name.item.value,
            time=event_time_local,
            reminders=[0] + reminders,
            invites=guests,
            mode=mode,
        )

        for user in guests:
            try:
                em = discord.Embed(title="⏰ **Event**", color=discord.Color.brand_green())
                em.add_field(
                    name="",
                    value=f"📅 **You were invited to {self.event_name.item.value}!** \n on {event_time_local.date()} at 🕒{event_time_local.time().strftime('%H:%M')}.",
                )
                em.set_footer(text="Please confirm your participation 👇.")
                await user.send(embed=em, view=ParticipationView(self.client, event_id))
            except discord.Forbidden:
                pass

        await interaction.response.send_message("✅ Event created and guests messaged!", ephemeral=True)


class EventEditModal(discord.ui.DesignerModal):
    def __init__(self, ctx: discord.ApplicationContext, client: Bot, event: Event, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = client
        self.event = event

        self.event_name = discord.ui.Label(
            "The name of the event.",
            discord.ui.InputText(
                placeholder="e.g. Game Night",
                value=self.event.name,
                required=True,
            ),
        )

        self.event_time = discord.ui.Label(
            "When will the event happen:",
            discord.ui.InputText(
                placeholder="TT.MM.JJJJ HH:MM",
                value=self.event.time.strftime("%d.%m.%Y %H:%M"),
                required=True,
            ),
        )

        options = []
        for reminder in REMINDER_BUTTONS:
            d_option = discord.SelectOption(label=reminder, value=str(REMINDER_BUTTONS[reminder]))
            options.append(d_option)

        reminders = []
        for reminder in event.reminders:
            inverted_reminder = {v: k for k, v in REMINDER_BUTTONS.items()}
            if reminder == 0:
                continue
            reminders.append(inverted_reminder[reminder])

        self.event_reminders = discord.ui.Label(
            "Select",
            discord.ui.Select(
                placeholder=f"Select a reminder, previous selected: {reminders}.",
                options=options,
                required=False,
                max_values=len(options),
            ),
        )

        options = []
        for mode in InviteMode:
            d_option = discord.SelectOption(label=mode.name, value=mode.value)
            options.append(d_option)

        if event.mode == InviteMode.OPEN.value:
            mode = InviteMode.OPEN.name
        elif event.mode == InviteMode.INVITE_ONLY.value:
            mode = InviteMode.INVITE_ONLY.name
        elif event.mode == InviteMode.CLOSED.value:
            mode = InviteMode.CLOSED.name

        self.event_mode = discord.ui.Label(
            "Invite Mode",
            discord.ui.Select(
                placeholder=f"Select an invite mode, previous selected: {mode}.",
                options=options,
                required=False,
            ),
        )

        self.add_item(self.event_name)
        self.add_item(self.event_time)
        self.add_item(self.event_reminders)
        self.add_item(self.event_mode)

    async def callback(self, interaction: discord.Interaction):
        updated_name = None
        if self.event.name != self.event_name.item.value:
            updated_name = self.event_name.item.value

        try:
            event_time_local = datetime.strptime(self.event_time.item.value.strip(), "%d.%m.%Y %H:%M")
            event_time_local = event_time_local.replace(tzinfo=SERVER_TZ)
            if event_time_local < datetime.now(tz=SERVER_TZ):
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                "Invalid date.\nPlease use: TT.MM.JJJJ HH:MM\nExample: 10.02.2026 18:00", ephemeral=True, delete_after=5
            )
            return

        updated_time = None
        if self.event.time.replace(tzinfo=SERVER_TZ) != event_time_local:
            updated_time = event_time_local

        updated_reminders = None
        if self.event_reminders.item.values != []:
            if self.event.reminders != [0] + list(map(int, self.event_reminders.item.values)):
                updated_reminders = [0] + list(map(int, self.event_reminders.item.values))

        updated_mode = None
        if self.event_mode.item.values != []:
            if self.event_mode.item.values[0] == InviteMode.OPEN.value:
                mode = InviteMode.OPEN.value
            elif self.event_mode.item.values[0] == InviteMode.INVITE_ONLY.value:
                mode = InviteMode.INVITE_ONLY.value
            else:
                mode = InviteMode.CLOSED.value
            if self.event.mode != mode:
                updated_mode = mode
        await self.client.db.update_event(
            id=self.event.id, name=updated_name, time=updated_time, reminders=updated_reminders, mode=updated_mode
        )
        updated_event = await self.client.db.get_event_by_id(self.event.id)
        if updated_time is not None:
            for user in updated_event.invites:
                try:
                    user_obj: discord.User = await self.client.get_or_fetch_user(user)
                    em = discord.Embed(title="⏰ **Event**", color=discord.Color.nitro_pink())
                    em.add_field(
                        name="",
                        value=f"📅 **The date of Event {updated_event.name}!** \n changed to {updated_event.time.replace(tzinfo=SERVER_TZ).date()} at 🕒{updated_event.time.replace(tzinfo=SERVER_TZ).time().strftime('%H:%M')}.",
                    )
                    em.set_footer(text="Please confirm your participation again 👇.")
                    await user_obj.send(embed=em, view=ParticipationView(self.client, self.event.id))
                except discord.Forbidden:
                    pass

        await interaction.response.send_message(
            "✅ Event updated and guests messaged!(if the date changed)", ephemeral=True
        )


class EventDeleteModal(discord.ui.DesignerModal):
    def __init__(self, ctx: discord.ApplicationContext, client: Bot, event: Event, error=False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = client
        self.event = event
        self.error = error

        self.event_delete = discord.ui.Label(
            "Type DELETE to cancel the event.",
            discord.ui.InputText(
                required=True,
                min_length=6,
                max_length=6,
            ),
        )

        self.delete_reason = discord.ui.Label(
            "Type the reason for the cancel.",
            discord.ui.InputText(
                required=False,
            ),
        )

        self.add_item(self.event_delete)
        self.add_item(self.delete_reason)

    async def callback(self, interaction: discord.Interaction):
        if self.event_delete.item.value != "DELETE":
            await interaction.response.send_message(
                f"❌ You misstyped DELETE.\nYou typed {self.event_delete.item.value}.",
                ephemeral=True,
                delete_after=5,
            )
        else:
            success = await self.client.db.delete_event(self.event.id)
            if success:
                invited_user = self.event.invites
                for user in invited_user:
                    user_obj: discord.User = await self.client.get_or_fetch_user(user)
                    if self.delete_reason.item.value == "":
                        em = discord.Embed(title="⏰ **Event canceled**", color=discord.Color.purple())
                        em.add_field(
                            name="",
                            value=f"📅 **The event {self.event.name} \non {self.event.time.date()} at 🕒{self.event.time.time().strftime('%H:%M')}\nhas been canceled!**",
                        )
                    else:
                        em = discord.Embed(title="⏰ **Event canceled**", color=discord.Color.purple())
                        em.add_field(
                            name="",
                            value=f"📅 **The event {self.event.name} \non {self.event.time.date()} at 🕒{self.event.time.time().strftime('%H:%M')}\nhas been canceled for the following reason:\n{self.delete_reason.item.value}!**",
                        )

                    await user_obj.send(embed=em)
                await interaction.response.send_message("✅ Event deleted.", ephemeral=True, delete_after=5)
            else:
                await interaction.response.send_message("❌ Something went wrong.", ephemeral=True, delete_after=5)


class EventReminder(commands.Cog):
    def __init__(self, client: Bot):
        self.client = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)

    @pycog.subcommand("event")
    @commands.slash_command(name="create", description="Create an event")
    async def create(self, ctx: discord.ApplicationContext):
        modal = EventReminderModal(ctx.guild, self.client, ctx.author, title="Create an Event")
        await ctx.response.send_modal(modal)

    @commands.Cog.listener("on_start_done")
    async def start_done(self):
        self.reminder_loop.start()

    @pycog.subcommand("event")
    @commands.slash_command(
        name="invite", description="Invite a user to an existing event", contexts={discord.InteractionContextType.guild}
    )
    async def invite(self, ctx: discord.ApplicationContext):
        events = await self.client.db.get_events()
        now = datetime.now(tz=SERVER_TZ)
        filtered_events = []
        for event in events:
            if event.time.replace(tzinfo=SERVER_TZ) > now:
                filtered_events.append(event)
        if filtered_events == []:
            await ctx.respond("Sry there are no future events", ephemeral=True, delete_after=5)
            return
        modal = EventInviteModal(ctx, self.client, filtered_events, title="Invite user to an event")
        await ctx.response.send_modal(modal)

    @pycog.subcommand("event")
    @commands.slash_command(
        name="request_invite",
        description="Request an invite to an event",
        contexts={discord.InteractionContextType.guild},
    )
    async def request_invite(self, ctx: discord.ApplicationContext):
        events = await self.client.db.get_events()
        now = datetime.now(tz=SERVER_TZ)
        filtered_events = []
        for event in events:
            already_invites = await self.client.db.get_all_confirmations_for_event(event_id=event.id)
            if ctx.interaction.user.id in already_invites and event.time.replace(tzinfo=SERVER_TZ) > now:
                filtered_events.append(event)
            elif event.time.replace(tzinfo=SERVER_TZ) > now:
                if not event.mode == InviteMode.CLOSED.value:
                    filtered_events.append(event)
        if filtered_events == []:
            await ctx.respond("Sry there are no future events", ephemeral=True, delete_after=5)
            return
        modal = EventRequestInviteModal(ctx, self.client, filtered_events, title="Request an invite to an event")
        await ctx.response.send_modal(modal)

    @pycog.subcommand("event")
    @commands.slash_command(
        name="edit", description="Edit an event that you created", contexts={discord.InteractionContextType.guild}
    )
    @discord.option(
        autocomplete=event_choices, name="event", description="Select the event you want to edit.", required=True
    )
    async def edit(self, ctx: discord.ApplicationContext, event: str):
        name = event.split(" | ")[0]
        time = datetime.strptime(event.split(" | ")[1], "%H:%M %d.%m.%Y").replace(tzinfo=SERVER_TZ)
        events = await self.client.db.get_events()
        selected_event = None
        for event in events:
            if event.name == name and event.time.replace(tzinfo=SERVER_TZ) == time:
                selected_event = event
                break

        modal = EventEditModal(client=self.client, ctx=ctx, event=selected_event, title=f"Edit {selected_event.name}")
        await ctx.interaction.response.send_modal(modal)

    @pycog.subcommand("event")
    @commands.slash_command(
        name="delete", description="Delete an event that you created", contexts={discord.InteractionContextType.guild}
    )
    @discord.option(
        autocomplete=event_choices, name="event", description="Select the event yxou want to edit.", required=True
    )
    async def delete(self, ctx: discord.ApplicationContext, event: str):
        name = event.split(" | ")[0]
        time = datetime.strptime(event.split(" | ")[1], "%H:%M %d.%m.%Y").replace(tzinfo=SERVER_TZ)
        events = await self.client.db.get_events()
        selected_event = None
        for event in events:
            if event.name == name and event.time.replace(tzinfo=SERVER_TZ) == time:
                selected_event = event
                break

        modal = EventDeleteModal(
            client=self.client, ctx=ctx, event=selected_event, error=False, title=f"Delete {selected_event.name}"
        )
        await ctx.interaction.response.send_modal(modal)

    @tasks.loop(seconds=30)
    async def reminder_loop(self):
        now = datetime.now(tz=SERVER_TZ)
        events = await self.client.db.get_events()

        for event in events:
            event_time = event.time.replace(tzinfo=SERVER_TZ)
            delta = (event_time - now).total_seconds()

            for reminder in event.reminders:
                if delta <= reminder:
                    event.reminders.remove(reminder)
                    for user_id in event.invites:
                        try:
                            user = await self.client.fetch_user(user_id)
                            em = discord.Embed(title="⏰ **Event**", color=discord.Color.brand_green())
                            if reminder == 0:
                                em.add_field(name="", value=f"**{event.name}** starts now!")
                            else:
                                em.add_field(name="", value=f"**{event.name}** starts in {reminder // 60} minute(s)")
                            await user.send(embed=em)
                        except discord.Forbidden:
                            pass

                        self.logger.info(f"Reminder for {event.id} send {reminder // 60} minutes before the event")
                    await self.client.db.update_event(id=event.id, reminders=event.reminders)


def setup(client):
    client.add_cog(EventReminder(client))
