import discord
from discord.ext import commands, tasks
import aiohttp
from discord.utils import get_or_fetch
from datetime import datetime
from config import SERVER_TZ


from utils import Bot, ButtonInfo, CustomLogger, SettingsEnum

#events = []
REMINDER_BUTTONS = {
    "1 Min": 60,
    "10 Min": 600,
    "1 Std": 3600,
    "1 Tag": 86400,
}

class ParticipationView(discord.ui.View):
    def __init__(self, client: Bot, event_id):
        super().__init__(timeout=None)
        self.client = client
        self.event_id = event_id

    async def _respond(self, interaction: discord.Interaction, status: bool):
        status_update = await self.client.db.update_confirmation(event_id=self.event_id, guest=interaction.user.id, confirmation=status)
        if status_update:
            await interaction.response.send_message(
                    f"✅ Deine Antwort **{"Zusage" if status else "Absage"}** wurde gespeichert.",
                    ephemeral=True
                )
        else:
            
            await interaction.response.send_message(
                    f"Something went wrong",
                    ephemeral=True
                )
        

    @discord.ui.button(label="✅ Zusagen", style=discord.ButtonStyle.success)
    async def accept(self, button, interaction: discord.Interaction):
        await self._respond(interaction, True)

    @discord.ui.button(label="❌ Absagen", style=discord.ButtonStyle.danger)
    async def decline(self, button, interaction: discord.Interaction):
        await self._respond(interaction, False)


class EventInviteModal(discord.ui.DesignerModal):
    def __init__(self,ctx: discord.ApplicationContext , client: Bot, events, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = client
        options = []
        self.events = events
        for event in self.events:
            if ctx.interaction.user.id == event["host"]:
                option = discord.SelectOption(label= event["name"] + " | " + str(event["time"].strftime('%H:%M %d.%m.%Y')), value=event["event_id"])
                options.append(option)
        
        self.event = discord.ui.Label(
            "Event",
            discord.ui.Select(
                placeholder="Select the Event you want invite to",
                required=True,
                options=options,
                min_values=1,
                max_values=1,
            )
        )
        self.invites = discord.ui.Label(
            "Invites",
            discord.ui.Select(
                select_type=discord.ComponentType.user_select,
                placeholder="Select all you want to invite",
                required=True,
                max_values=25
            ),
        )
        self.add_item(self.event)
        self.add_item(self.invites)

    async def callback(self, interaction):
        event_id = self.event.item.values[0]
        event_obj = await self.client.db.get_event_by_id(event_id=event_id)
        invites = self.invites.item.values
        try:
            for invite in invites:
                already_invites = await self.client.db.get_all_confirmations_for_event(event_id=event_id)
                if invite.id not in already_invites:
                    await self.client.db.create_confirmation(event_id=event_id, guest=invite.id, confirmation=None)
                
                em = discord.Embed(title=f"⏰ **Event**", color=discord.Color.brand_green())
                em.add_field(name="",value=f"📅 **Du wurdest zu {event_obj["name"]} eingeladen!** \n am {event_obj["time"].date()} um 🕒{event_obj["time"].time().strftime('%H:%M')} ")
                em.set_footer(text="Bitte bestätige deine Teilnahme 👇")
                await invite.send(
                    embed=em,
                    view=ParticipationView(self.client, event_id)
                )
                await interaction.respond(
                        f"{invite} was invited to the event",
                        ephemeral=True,
                        delete_after=5,
                    )
        except discord.Forbidden:
                await interaction.respond(
                        f"{invite} was invited not to the event, because the user not allows dm's",
                        ephemeral=True,
                        delete_after=5,
                    )
                pass  # DMs geschlossen

class EventReminderModal(discord.ui.DesignerModal):
    def __init__(
        self,
        guild: discord.Guild,
        client: Bot,
        host,
        *args,
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.guild = guild
        self.client = client
        self.host = host

        self.event_name = discord.ui.Label(
            "The name of the event.",
            discord.ui.InputText(
                placeholder="e.g. Game Night"
            ),
        )
        
        self.event_time = discord.ui.Label(
            "When will the event happen:",
            discord.ui.InputText(
                placeholder="TT.MM.JJJJ HH:MM"
            ),
        )
        
        self.event_guests = discord.ui.Label(
            "Guests",
            discord.ui.Select(
                select_type=discord.ComponentType.user_select,
                placeholder="Select all you want to invite",
                required=True,
                max_values=25
            ),
        )
            
        options = []
        for reminder in REMINDER_BUTTONS:
            d_option = discord.SelectOption(label=reminder, value=str(REMINDER_BUTTONS[reminder]))
            options.append(d_option)
        self.event_reminders = discord.ui.Label(
            "Select",
            discord.ui.Select(
                placeholder="Select a reminder",
                options=options,
                required=True,
                max_values=len(options)
            ),
        )
        
        self.add_item(self.event_name)
        self.add_item(self.event_time)
        self.add_item(self.event_guests)
        self.add_item(self.event_reminders)

    async def callback(self, interaction: discord.Interaction):
        try:
            event_time_local = datetime.strptime(
                self.event_time.item.value.strip(),
                "%d.%m.%Y %H:%M"
            )
            event_time_local = event_time_local.replace(tzinfo=SERVER_TZ)
        except ValueError:
            await interaction.response.send_message(
                "Ungültiges Datum.\nBitte nutze: TT.MM.JJJJ HH:MM\nBeispiel: 10.02.2026 18:00",
                ephemeral=True,
                delete_after=5
            )
            return
        guests = []
        for guest in self.event_guests.item.values:
            guests.append(guest)
        reminders = list(map(int, self.event_reminders.item.values))

        
        event_id = await self.client.db.create_event(
            host=self.host.id, 
            event_name=self.event_name.item.value,
            time=event_time_local,
            reminders=[0] + reminders,
            invites=guests
            )

        # 🔔 Sofort-Benachrichtigung
        for user in guests:
            try:
                em = discord.Embed(title=f"⏰ **Event**", color=discord.Color.brand_green())
                em.add_field(name="",value=f"📅 **Du wurdest zu {self.event_name.item.value} eingeladen!** \n am {event_time_local.date()} um 🕒{event_time_local.time().strftime('%H:%M')} ")
                em.set_footer(text="Bitte bestätige deine Teilnahme 👇")
                await user.send(
                    embed=em,
                    view=ParticipationView(self.client, event_id)
                )
            except discord.Forbidden:
                pass  # DMs geschlossen

        await interaction.response.send_message(
            "✅ Event erstellt & Teilnehmer benachrichtigt!",
            ephemeral=True
        )


class EventReminder(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)
        self.events = {}
    
    @commands.slash_command(
    name="reminder",
    description="Remind people of an event"
    )
    async def reminder(self, ctx: discord.ApplicationContext):
        modal = EventReminderModal(
            ctx.guild,
            self.client,
            ctx.author,
            title="Event Reminder"
        )
        await ctx.response.send_modal(modal)
    
    @commands.Cog.listener("on_start_done")
    async def start_done(self):
        self.reminder_loop.start()
    
    @commands.slash_command(
            name="invite", description="Invite a user to an existing event", contexts={discord.InteractionContextType.guild}
    )
    async def invite(self, ctx: discord.ApplicationContext):
        events = await self.client.db.get_events()
        now = datetime.now(tz=SERVER_TZ)
        filtered_events = []
        for event in events:
            if event["time"].replace(tzinfo=SERVER_TZ) > now:
                filtered_events.append(event)
        modal = EventInviteModal(
            ctx,
            self.client,
            filtered_events,
            title="Event Invite"
        )
        await ctx.response.send_modal(modal)
        

    @tasks.loop(seconds=30)
    async def reminder_loop(self):
        now = datetime.now(tz=SERVER_TZ)  # tz-aware aktuelle Server-Zeit
        events = await self.client.db.get_events()

        for event in events:
            event_time = event["time"].replace(tzinfo=SERVER_TZ)
            delta = (event_time - now).total_seconds()
            #print(event["users"])

            for reminder in event["reminders"]:
                if delta <= reminder:
                    event["reminders"].remove(reminder)
                    for user_id in event["users"]:
                            try:
                                user = await self.client.fetch_user(user_id)
                                em = discord.Embed(title=f"⏰ **Erinnerung**", color=discord.Color.brand_green())
                                if reminder == 0:
                                    em.add_field(name="",value=f"**{event['name']}** beginnt jetzt!")
                                else:
                                    em.add_field(name="",value=f"**{event['name']}** beginnt in {reminder // 60} Minute(n)")
                                self.logger.info(f"Reminder sent to {user.id}, {reminder// 60} minutes before the event")
                                await user.send(
                                    embed=em
                                )
                            except discord.Forbidden:
                                pass

                    await self.client.db.update_event(event_id=event["event_id"], reminders=event["reminders"])


def setup(client):
    client.add_cog(EventReminder(client))
