import discord
from discord.ext import commands, tasks
import aiohttp
from discord.utils import get_or_fetch
from datetime import datetime
from config import SERVER_TZ

from utils import Bot, ButtonInfo, CustomLogger, SettingsEnum

events = []
REMINDER_BUTTONS = {
    "1 Min": 60,
    "10 Min": 600,
    "1 Std": 3600,
    "1 Tag": 86400,
}

class ReminderButton(discord.ui.Button):
    def __init__(self, label: str, seconds: int):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.secondary
        )
        self.seconds = seconds

    async def callback(self, interaction: discord.Interaction):
        view: Event_ReminderView = self.view

        if self.seconds in view.selected_reminders:
            # deaktivieren
            view.selected_reminders.remove(self.seconds)
            self.style = discord.ButtonStyle.secondary
        else:
            # aktivieren
            view.selected_reminders.add(self.seconds)
            self.style = discord.ButtonStyle.success

        await interaction.response.edit_message(view=view)


class Event_ReminderView(discord.ui.View):
    def __init__(self, guild: discord.Guild, client: Bot):
        super().__init__(timeout=60)
        self.guild = guild
        self.client = client

        self.selected_users: list[discord.Member] = []
        self.selected_reminders: set[int] = set()

        # Reminder Buttons hinzufügen
        for label, seconds in REMINDER_BUTTONS.items():
            self.add_item(ReminderButton(label, seconds))

    @discord.ui.user_select(
        placeholder="👥 Teilnehmer auswählen",
        min_values=1,
        max_values=15
    )
    async def user_select(self, select, interaction: discord.Interaction):
        self.selected_users = select.values
        await interaction.response.defer()

    @discord.ui.button(label="Weiter", style=discord.ButtonStyle.primary, row=3)
    async def continue_button(self, button, interaction: discord.Interaction):
        if not self.selected_users:
            await interaction.response.send_message(
                "❌ Bitte wähle mindestens einen Nutzer aus.",
                ephemeral=True
            )
            return

        if not self.selected_reminders:
            await interaction.response.send_message(
                "❌ Bitte wähle mindestens eine Erinnerungszeit aus.",
                ephemeral=True
            )
            return

        modal = Event_ReminderModal(
            self.guild,
            self.client,
            self.selected_users,
            list(self.selected_reminders),
            title="Event Reminder"
        )
        await interaction.response.send_modal(modal)

    async def on_timeout(self):
        await self.message.delete()



class Event_ReminderModal(discord.ui.Modal):
    def __init__(
        self,
        guild: discord.Guild,
        client: Bot,
        users: list[discord.Member],
        reminders,
        *args,
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.guild = guild
        self.client = client
        self.users = users
        self.reminders = reminders

        self.event_name = discord.ui.InputText(
            label="Event name",
            placeholder="e.g. Game Night"
        )
        self.event_time = discord.ui.InputText(
            label=f"Date & time(depends on ST)",
            placeholder="TT.MM.JJJJ HH:MM"
        )

        self.add_item(self.event_name)
        self.add_item(self.event_time)

    async def callback(self, interaction: discord.Interaction):
        try:
            event_time_local = datetime.strptime(
                self.event_time.value.strip(),
                "%d.%m.%Y %H:%M"
            )
        except ValueError:
            await interaction.response.send_message(
                "Ungültiges Datum.\nBitte nutze: TT.MM.JJJJ HH:MM\nBeispiel: 10.02.2026 18:00",
                ephemeral=True,
                delete_after=5
            )
            return
        event_time_local = event_time_local.replace(tzinfo=SERVER_TZ)
        event = {
            "name": self.event_name.value,
            "time": event_time_local,
            "users": [u.id for u in self.users],
            "reminders": [0] + self.reminders,
            "sent": set()
        }

        events.append(event)

        # 🔔 Sofort-Benachrichtigung
        for user in self.users:
            try:
                em = discord.Embed(title=f"⏰ **Event**", color=discord.Color.brand_green())
                em.add_field(name="",value=f"📅 **Du wurdest zu {event['name']} eingeladen!** \n am {event_time_local.date()} um 🕒{event_time_local.time()} ")
                await user.send(
                    embed=em
                )
            except discord.Forbidden:
                pass  # DMs geschlossen

        await interaction.response.send_message(
            "✅ Event erstellt & Teilnehmer benachrichtigt!",
            ephemeral=True,
            delete_after=10
        )



class Event_Reminder(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)
        self.events = {}
        self.reminder_loop.start()
    
    @commands.slash_command(
    name="reminder",
    description="Remind people of an event"
    )
    async def reminder(self, ctx: discord.ApplicationContext):
        view = Event_ReminderView(ctx.guild, self.client)
        await ctx.respond(
            "👥 Select users to remind:",
            view=view,
            ephemeral=True,
        )
    
    @tasks.loop(seconds=30)
    async def reminder_loop(self):
        now = datetime.now(tz=SERVER_TZ)  # tz-aware aktuelle Server-Zeit

        for event in events:
            delta = (event["time"] - now).total_seconds()

            for reminder in event["reminders"]:
                if delta <= reminder and reminder not in event["sent"]:
                    for user_id in event["users"]:
                        try:
                            user = await self.client.fetch_user(user_id)
                            em = discord.Embed(title=f"⏰ **Erinnerung**", color=discord.Color.brand_green())
                            if reminder == 0:
                                em.add_field(name="",value=f"**{event['name']}** beginnt jetzt!")
                            else:
                                em.add_field(name="",value=f"**{event['name']}** beginnt in {reminder // 60} Minute(n)")
                            await user.send(
                                embed=em
                            )
                        except discord.Forbidden:
                            pass

                    event["sent"].add(reminder)


def setup(client):
    client.add_cog(Event_Reminder(client))
