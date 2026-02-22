from collections.abc import Sequence
from datetime import datetime

import discord
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config import DATABASE_URL

from ..enums import InfractionsEnum, SettingsEnum, StatTypeEnum
from ..logger import CustomLogger
from .models import Base, BotStatus, Infractions, Join2Create, Modmail, Settings, UserStats, EnabledCommands, Events, Confirmation


class ORMDataBase:
    """
    ORMDataBase class handles the asynchronous database operations using SQLAlchemy.
    """

    def __init__(self):
        """
        Initializes the ORMDataBase instance with an async engine and session maker.
        """
        self.logger: CustomLogger = None  # type: ignore
        self.engine: AsyncEngine = create_async_engine(DATABASE_URL)
        self.AsyncSessionLocal: AsyncSession = async_sessionmaker(self.engine, expire_on_commit=False)  # type: ignore

    async def setup(self, boot: datetime):
        """
        Sets up the database by creating new tables if they don't already exist.

        Args:
            boot (datetime): The boot time of the application.
        """
        self.logger = CustomLogger("database", boot)  # type: ignore
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            self.logger.info("ContentDB tables created and ready to use!")

    async def close(self):
        """
        Closes the database connection and disposes of the engine.
        """
        self.logger.warning("Closing database connection")
        await self.engine.dispose()

    async def get_setting(
        self, setting: SettingsEnum, guild: discord.Guild | None
    ) -> None | Settings | Sequence[Settings]:
        """
        Retrieves a setting from the database.

        Args:
            setting (SettingsEnum): The setting to retrieve.
            guild (discord.Guild | None): The guild associated with the setting. If None, retrieves the setting for all guilds.

        Returns:
            Sequence[Settings] | None: The retrieved setting(s) or None if not found.
        """
        async with self.AsyncSessionLocal() as session:
            async with session.begin():
                if guild is None:
                    query = select(Settings).where(Settings.setting == setting.value)
                else:
                    query = select(Settings).where(Settings.setting == setting.value, Settings.guild == guild.id)
                response = await session.execute(query)
                results = response.scalars().fetchall()
        if not results:
            return None
        elif len(results) == 1:
            return results[0]
        else:
            return results

    async def update_setting(self, setting: SettingsEnum, value: int, guild: discord.Guild) -> None:
        """
        Updates a setting in the database.

        Args:
            setting (SettingsEnum): The setting to update.
            value (int): The new value of the setting.
            guild (discord.Guild | None): The guild associated with the setting. If None, updates the setting for all guilds.
        """
        async with self.AsyncSessionLocal() as session:
            async with session.begin():
                query = select(Settings).where(Settings.setting == setting.value, Settings.guild == guild.id)
                db_setting = (await session.execute(query)).scalar_one_or_none()
                if db_setting is None:
                    session.add(Settings(setting=setting.value, value=value, guild=guild.id))
                else:
                    db_setting.value = value
            await session.commit()

    async def delete_setting(self, setting: SettingsEnum, guild: discord.Guild) -> None:
        """
        Deletes a setting from the database.

        Args:
            setting (SettingsEnum): The setting to delete.
            guild (discord.Guild): The guild associated with the setting.
        """
        async with self.AsyncSessionLocal() as session:
            async with session.begin():
                query = select(Settings).where(Settings.setting == setting.value, Settings.guild == guild.id)
                db_setting = (await session.execute(query)).scalar_one_or_none()
                if db_setting is None:
                    return None
                else:
                    await session.delete(db_setting)
                await session.commit()

    async def create_temp_voice(self, channel: discord.VoiceChannel, owner: discord.Member) -> Join2Create | None:
        async with self.AsyncSessionLocal() as session:
            async with session.begin():
                new_entry = Join2Create(channel=channel.id, owner_id=owner.id, locked=False, ghosted=False)
                session.add(new_entry)
            await session.refresh(new_entry)
            result = await session.get(Join2Create, channel.id)
            return result

    async def update_temp_voice(
        self, channel: discord.VoiceChannel, owner: discord.Member, locked: bool, ghosted: bool
    ):
        async with self.AsyncSessionLocal() as session:
            async with session.begin():
                query = select(Join2Create).where(Join2Create.channel == channel.id)
                _channel = (await session.execute(query)).scalar_one_or_none()
                _channel.owner_id = owner.id
                _channel.locked = locked
                _channel.ghosted = ghosted
                await session.commit()

    async def get_temp_voice(self, channel: discord.VoiceChannel) -> None | Join2Create:
        async with self.AsyncSessionLocal() as session:
            async with session.begin():
                query = select(Join2Create).where(Join2Create.channel == channel.id)
                temp_channel = (await session.execute(query)).scalar_one_or_none()
        return temp_channel

    async def delete_temp_voice(self, channel: discord.VoiceChannel):
        async with self.AsyncSessionLocal() as session:
            async with session.begin():
                query = select(Join2Create).where(Join2Create.channel == channel.id)
                temp_channel = (await session.execute(query)).scalar_one_or_none()
                await session.delete(temp_channel)
                await session.commit()

    async def create_infraction(
        self, user: discord.User | discord.Member, infraction: InfractionsEnum, reason: str, guild: discord.Guild
    ) -> int:
        """
        Creates a new infraction record in the database.

        Args:
            user (discord.User | discord.Member): The user who received the infraction.
            infraction (InfractionsEnum): The type of infraction.
            reason (str): The reason for the infraction.
            guild (discord.Guild): The guild where the infraction occurred.

        Returns:
            int: The case ID of the created infraction.
        """
        async with self.AsyncSessionLocal() as session:
            async with session.begin():
                infraction = Infractions(
                    user_id=user.id, infraction=infraction.value, reason=reason, date=datetime.now(), guild=guild.id
                )
                session.add(infraction)
                await session.commit()
                return infraction.case_id

    async def update_infraction(self):
        raise NotImplementedError("In the past this had no use!")

    async def get_infraction(
        self, case_id: int | None, user: discord.Member | discord.User | None, guild: discord.Guild | None = None
    ) -> None | Infractions | Sequence[Infractions]:
        """
        Retrieves infraction(s) from the database based on case ID or user.

        Args:
            case_id (int | None): The case ID of the infraction to retrieve. If None, retrieves by user.
            user (discord.Member | discord.User | None): The user whose infractions to retrieve. Used if case_id is None.
            guild (discord.Guild | None): The guild associated with the infraction. Not used in this method.

        Returns:
            None | Infractions | Sequence[Infractions]: Returns None if no infractions are found,
            a single Infractions object if one is found, or a sequence of Infractions if multiple are found.

        Raises:
            LookupError: If both case_id and user are None.
        """
        async with self.AsyncSessionLocal() as session:
            async with session.begin():
                if case_id:
                    query = select(Infractions).where(Infractions.case_id == case_id)
                elif user:
                    query = select(Infractions).where(Infractions.user_id == user.id)
                else:
                    raise LookupError("Both arguments are 'None'. At least one must have a value!")
                infractions = (await session.execute(query)).scalars().all()
        if len(infractions) == 0:
            return None
        if len(infractions) == 1:
            return infractions[0]
        return infractions

    async def create_modmail(
        self, user: discord.User | discord.Member, guild: discord.Guild, uuid: str, anonymous: bool
    ):
        async with self.AsyncSessionLocal() as session:
            async with session.begin():
                session.add(
                    Modmail(
                        user_id=user.id,
                        guild_id=guild.id,
                        uuid=uuid,
                        anon=anonymous,
                    )
                )

    async def get_modmail(self, user: discord.User | discord.Member | None, uuid: str | None) -> None | Modmail:
        async with self.AsyncSessionLocal() as session:
            async with session.begin():
                if user:
                    query = select(Modmail).where(Modmail.user_id == user.id)
                elif uuid:
                    query = select(Modmail).where(Modmail.uuid == uuid)
                else:
                    raise LookupError("Both arguments are 'None'. At least one must have a value!")
                modmail = (await session.execute(query)).scalar_one_or_none()
        return modmail

    async def delete_modmail(self, user: discord.User | discord.Member) -> None:
        async with self.AsyncSessionLocal() as session:
            async with session.begin():
                query = select(Modmail).where(Modmail.user_id == user.id)
                result = (await session.execute(query)).scalar()
                if result is None:
                    return
                await session.delete(result)
                await session.commit()

    async def update_user_stat(self, user: discord.Member, stat_type: StatTypeEnum, value: int, guild: discord.Guild):
        async with self.AsyncSessionLocal() as session:
            async with session.begin():
                query = select(UserStats).where(
                    UserStats.user_id == user.id, UserStats.stat_type == stat_type.value, UserStats.guild_id == guild.id
                )
                result = (await session.execute(query)).scalar_one_or_none()
                if result is None:
                    session.add(UserStats(user_id=user.id, stat_type=stat_type.value, value=value, guild_id=guild.id))
                else:
                    result.value += value
                await session.commit()

    async def get_user_stat(
        self, user: discord.User | discord.Member | None, stat_type: StatTypeEnum, guild: discord.Guild | None
    ) -> None | UserStats | Sequence[UserStats]:
        async with self.AsyncSessionLocal() as session:
            async with session.begin():
                if user and guild:
                    query = select(UserStats).where(
                        UserStats.user_id == user.id,
                        UserStats.stat_type == stat_type.value,
                        UserStats.guild_id == guild.id,
                    )
                elif user:
                    query = select(UserStats).where(
                        UserStats.user_id == user.id, UserStats.stat_type == stat_type.value
                    )
                elif guild:
                    query = select(UserStats).where(
                        UserStats.stat_type == stat_type.value, UserStats.guild_id == guild.id
                    )
                else:
                    raise LookupError("'User' and 'Guild' arguments are 'None'. At least one must have a value!")
                userstats = (await session.execute(query)).scalars().all()
        if len(userstats) == 0:
            return None
        if len(userstats) == 1:
            return userstats[0]
        return userstats

    async def delete_user_stat(self, user: discord.User | None, guild: discord.Guild | None):
        async with self.AsyncSessionLocal() as session:
            async with session.begin():
                if user and guild:
                    query = select(UserStats).where(UserStats.user_id == user.id, UserStats.guild_id == guild.id)
                elif user:
                    query = select(UserStats).where(UserStats.user_id == user.id)
                elif guild:
                    query = select(UserStats).where(UserStats.guild_id == guild.id)
                else:
                    raise LookupError("'User' and 'Guild' arguments are 'None'. At least one must have a value!")
                userstats = (await session.execute(query)).scalars().all()
                if len(userstats) == 0:
                    return
                if len(userstats) == 1:
                    await session.delete(userstats)
                else:
                    for userstat in userstats:
                        await session.delete(userstat)

    async def create_bot_status(self, activity_type: discord.ActivityType, status: discord.Status, activity_name: str):
        async with self.AsyncSessionLocal() as session:
            async with session.begin():
                session.add(
                    BotStatus(activity_type=int(activity_type), status=str(status), activity_name=activity_name)
                )
                await session.commit()

    async def edit_bot_status(
        self,
        id_: int,
        activity_type: discord.ActivityType = None,
        status: discord.Status = None,
        activity_name: str = None,
    ) -> None:
        async with self.AsyncSessionLocal() as session:
            async with session.begin():
                query = select(BotStatus).where(BotStatus.id == id_)
                result = (await session.execute(query)).scalar_one_or_none()
                if result is None:
                    return None
                result.activity_type = int(activity_type) if activity_type else result.activity_type
                result.status = str(status) if status else result.status
                result.activity_name = activity_name if activity_name else result.activity_name
                await session.commit()

    async def get_bot_status(self, id_: int | None) -> BotStatus | Sequence[BotStatus] | None:
        """
        Gets the bot status from the database.
        Args:
            id_:

        Returns:
            A BotStatus object, a list of it or None. The BotStatus object uses py-cords enums for activity_type and
            status. You will have to convert them to the correct type, to use them effectively.
        """
        async with self.AsyncSessionLocal() as session:
            async with session.begin():
                if id_:
                    query = select(BotStatus).where(BotStatus.id == id_)
                else:
                    query = select(BotStatus)
                bot_status = (await session.execute(query)).scalars().all()
        if len(bot_status) == 0:
            return None
        if len(bot_status) == 1:
            return bot_status[0]
        return bot_status

    async def delete_bot_status(self, id_: int):
        async with self.AsyncSessionLocal() as session:
            async with session.begin():
                query = select(BotStatus).where(BotStatus.id == id_)
                result = (await session.execute(query)).scalar_one_or_none()
                if result is None:
                    return
                await session.delete(result)
                await session.commit()

    async def is_command_enabled(self, guild: discord.Guild, command_name: str) -> bool:
        """
        Checks if a specific command is enabled for a given guild.

        Args:
            guild: The Discord guild to check the command status for.
            command_name: The name of the command to check.

        Returns:
            True if the command is enabled for the guild, or if no record exists (default enabled).
            False if the command is explicitly disabled.
        """
        async with self.AsyncSessionLocal() as session:
            async with session.begin():
                query = select(EnabledCommands).where(
                    EnabledCommands.guild_id == guild.id, EnabledCommands.command_name == command_name
                )
                result: EnabledCommands | None = (await session.execute(query)).scalar_one_or_none()
                if result is None:
                    return True
                return bool(result.enabled)

    async def toggle_command(self, guild: discord.Guild, command_name: str) -> bool:
        """
        Toggles the enabled status of a command for a guild.
        Args:
            guild: The guild the command is being toggled in.
            command_name: the fully qualified name of the command to toggle.

        Returns: The new state of the command (enabled/disabled).
        """
        async with self.AsyncSessionLocal() as session:
            async with session.begin():
                query = select(EnabledCommands).where(
                    EnabledCommands.guild_id == guild.id, EnabledCommands.command_name == command_name
                )
                result: EnabledCommands | None = (await session.execute(query)).scalar_one_or_none()
                new_state: bool
                if result is None:
                    obj = EnabledCommands(guild_id=guild.id, command_name=command_name, enabled=False)
                    session.add(obj)
                    new_state = False  # Command not in DB means it was enabled; now disabling it
                else:
                    result.enabled = not bool(result.enabled)
                    new_state = bool(result.enabled)
                await session.commit()
                return new_state

    async def create_confirmation(self, *, event_id: str, guest: int, confirmation: bool) -> None:
        """
        Creates a new confirmation for an event
        Args:
            event_id: Unique id for every event.
            guest: User id of the invited guest.
            confirmation: The guests respond (None if pending)

        Returns: None
        """
        async with self.AsyncSessionLocal() as session:
            async with session.begin():
                session.add(
                    Confirmation(event_id=event_id, user_id=guest, confirmation=confirmation)
                )
                await session.commit()
                self.logger.debug(f"Confirmation for {event_id} and user {guest} created")
    
    async def update_confirmation(self, *, event_id: str, guest: int, confirmation: bool) -> bool:
        """
        Creates a new confirmation for an event
        Args:
            event_id: Unique id for every event.
            guest: User id of the invited guest.
            confirmation: The guests respond (None if pending)

        Returns: None
        """
        try:
            async with self.AsyncSessionLocal() as session:
                async with session.begin():
                    confirmation_obj: Confirmation = await session.get(Confirmation, (event_id, guest))
                    confirmation_obj.confirmation = confirmation
                    await session.commit()
                    self.logger.debug(f"Confirmation for {event_id} and user {guest} updated to {confirmation}")
                    return True
        except SQLAlchemyError:
            return False
    
    async def get_confirmations_for_event(self, *, event_id: str) -> list[int]:
        """
        Gets all user that accepted the invitation for the event 
        Args:
            event_id: ID of the event

        Returns: List of all users that accepted the invitation
        """
        async with self.AsyncSessionLocal() as session:
            async with session.begin():
                query = select(Confirmation.user_id).where(
                    Confirmation.event_id == event_id,
                    Confirmation.confirmation.is_(True)
                )
                users_ids = (await session.execute(query)).scalars().all()
                return users_ids
    
    async def get_all_confirmations_for_event(self, *, event_id: str) -> list[int]:
        """
        Gets all user that were invited to the event 
        Args:
            event_id: ID of the event

        Returns: List of all users that were invited
        """
        async with self.AsyncSessionLocal() as session:
            async with session.begin():
                query = select(Confirmation.user_id).where(
                    Confirmation.event_id == event_id
                )
                users_ids = (await session.execute(query)).scalars().all()
                return users_ids

    async def create_event(self, *, host: int, event_name: str, time: datetime, reminders: list[int], invites: list[int]) -> str:
        """
        Creates a new event
        Args:
            host: User id of the host of the event.
            event_name: Name of the event.
            time: Time when the event happens.
            reminders: List of reminders set for the event f.e. [0, 60, ...] in s

        Returns: The event_id to identify the event.
        """
        async with self.AsyncSessionLocal() as session:
            async with session.begin():
                event_id = str(host) + str(time)
                reminders_db = ",".join(map(str, reminders))
                session.add(
                    Events(event_id=str(event_id), host=int(host), event_name=str(event_name), time=time, reminders=str(reminders_db))
                )
                await session.commit()
                for invite in invites:
                    await self.create_confirmation(event_id=event_id, guest=invite.id, confirmation=None)
            self.logger.debug(f"Event created {event_id}")
            return event_id

    async def get_event_by_id(self, event_id: str) -> dict:
        """
        Gets an event by an event_id
        Args:

        Returns:
            An event as dict (so i dont have to rewrite the reminder logic ^^)
        """
        async with self.AsyncSessionLocal() as session:
            async with session.begin():
                event = await session.get(Events, event_id)
                users = await self.get_confirmations_for_event(event_id=event_id)
        if event is None:
            return {}
        if event.reminders == "":
            reminders_t = []
        else:
            reminders_t = list(map(int, event.reminders.split(",")))
        event_t = {
            "event_id": event.event_id,
            "host": event.host,
            "name": event.event_name,
            "time": event.time,
            "users": users,
            "reminders": reminders_t,
        }
        return event_t

    async def get_events(self) -> list[dict]:
        """
        Gets all events
        Args:

        Returns:
            All events as a dict (so i dont have to rewrite the reminder logic ^^)
        """
        async with self.AsyncSessionLocal() as session:
            async with session.begin():
                query = select(Events)
                events = (await session.execute(query)).scalars().all()
        events_r = []
        for event in events:
            users = await self.get_confirmations_for_event(event_id=event.event_id)
            if event.reminders == "":
                reminders_t = []
            else:
                reminders_t = list(map(int, event.reminders.split(",")))
            
            event_t = {
                "event_id": event.event_id,
                "host": event.host,
                "name": event.event_name,
                "time": event.time,
                "users": users,
                "reminders": reminders_t,
            }
            events_r.append(event_t)
        return events_r
    
    async def update_event(self, *, event_id: str, host: int | None = None, event_name: str | None = None, time: datetime | None = None, reminders: list[int] | None = None) -> bool:
        """
        Updates an event
        Args:
            event_id: Unique id for an event.
            host: User id of the host of the event.
            event_name: Name of the event.
            time: Time when the event happens.
            reminders: List of reminders set for the event f.e. [0, 60, ...] in s

        Returns: The event_id to identify the event.
        """
        try:
            async with self.AsyncSessionLocal() as session:
                async with session.begin():
                    event = await session.get(Events, event_id)
                    if event is None:
                        return False
                    if host is not None:
                        event.host = host
                    if event_name is not None:
                        event.event_name = event_name
                    if time is not None:
                        event.time = time
                    if reminders is not None:
                        reminders_db = ",".join(map(str, reminders))
                        event.reminders = reminders_db
                    await session.commit()
            self.logger.debug(f"Event {event_id} updated")
            return True
        except SQLAlchemyError:
            return False
