from datetime import datetime
import typing as t

import discord
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from config import SERVER_TZ
from utils.classes import Confirmation, Event
from utils.logger import CustomLogger
from utils.orm_database.repository import BaseRepository

from .models import ConfirmationDB, Events

__all__ = ["EventRepository"]


class EventRepository(BaseRepository):
    """Repository for Event and Confirmation operations."""

    def __init__(self, session_maker: async_sessionmaker[AsyncSession], logger: CustomLogger | None = None):
        super().__init__(session_maker)
        self.logger = logger

    def _log_info(self, message: str) -> None:
        if self.logger is not None:
            self.logger.info(message)

    def _log_error(self, message: str) -> None:
        if self.logger is not None:
            self.logger.error(message)

    async def create_confirmation(
        self, *, event_id: str, guest: int, confirmation: bool | None, reminders: list[int]
    ) -> None:
        """
        Creates a new confirmation for an event
        Args:
            event_id: Unique id for every event.
            guest: User id of the invited guest.
            confirmation: The guests respond (None if pending)
            reminders: when the guest will be reminded before the event

        Returns: None
        """
        async with self.session() as session:
            reminders_db = ",".join(map(str, reminders))
            session.add(
                ConfirmationDB(event_id=event_id, user_id=guest, confirmation=confirmation, reminders=reminders_db)
            )
        self._log_info(f"Confirmation for {event_id} and user {guest} created")

    async def update_confirmation(
        self, *, event_id: str, guest: int, confirmation: bool | None = None, reminders: list[int] | None = None
    ) -> bool:
        """
        Updates a confirmation for an event
        Args:
            event_id: Unique id for every event.
            guest: User id of the invited guest.
            confirmation: The guests respond (None if pending)
            reminders: when the guest will be reminded before the event

        Returns: bool
        """
        try:
            async with self.session() as session:
                confirmation_obj: ConfirmationDB | None = await session.get(ConfirmationDB, (event_id, guest))
                if confirmation_obj is None:
                    return False
                if confirmation is not None:
                    confirmation_obj.confirmation = confirmation
                if reminders is not None:
                    confirmation_obj.reminders = ",".join(map(str, reminders))
            self._log_info(
                f"Confirmation for {event_id} and user {guest} updated to {confirmation} and/or reminders to {confirmation_obj.reminders}"
            )
            return True
        except SQLAlchemyError:
            return False

    async def get_confirmation_for_event_and_user(self, *, event_id: str, guest: int) -> Confirmation | None:
        """
        Gets the confirmation for a user invited to the event
        Args:
            event_id: ID of the event
            guest: ID of the user

        Returns: The confirmation for this event and that user
        """
        async with self.session() as session:
            confirm: ConfirmationDB | None = await session.get(ConfirmationDB, (event_id, guest))
            if confirm is None:
                self._log_error(f"Confirmation not found by event_id {event_id} and user {guest}")
                return None
            reminders = [] if confirm.reminders == "" else list(map(int, confirm.reminders.split(",")))
            return Confirmation(
                event_id=confirm.event_id,
                guest=confirm.user_id,
                confirmation=confirm.confirmation,
                reminders=reminders,
            )

    async def get_confirmations_for_event(self, *, event_id: str) -> list[int]:
        """
        Gets all user that accepted the invitation for the event
        Args:
            event_id: ID of the event

        Returns: List of all users that accepted the invitation
        """
        async with self.session() as session:
            query = select(ConfirmationDB.user_id).where(
                ConfirmationDB.event_id == event_id, ConfirmationDB.confirmation.is_(True)
            )
            users_ids = (await session.execute(query)).scalars().all()
            return list(users_ids)

    async def get_complete_confirmations_for_event(self, *, event_id: str) -> list[Confirmation]:
        """
        Gets all user that accepted the invitation for the event
        Args:
            event_id: ID of the event

        Returns: List of all confirmations that accepted the invitation
        """
        async with self.session() as session:
            query = select(ConfirmationDB).where(
                ConfirmationDB.event_id == event_id, ConfirmationDB.confirmation.is_(True)
            )
            confirmations = (await session.execute(query)).scalars().all()
            res = []
            for confirmation in confirmations:
                reminders = [] if confirmation.reminders == "" else list(map(int, confirmation.reminders.split(",")))
                new_conf = Confirmation(
                    event_id=confirmation.event_id,
                    guest=confirmation.user_id,
                    confirmation=confirmation.confirmation,
                    reminders=reminders,
                )
                res.append(new_conf)
            return res

    async def get_all_confirmations_for_event(self, *, event_id: str) -> list[int]:
        """
        Gets all user that were invited to the event
        Args:
            event_id: ID of the event

        Returns: List of all users that were invited
        """
        async with self.session() as session:
            query = select(ConfirmationDB.user_id).where(ConfirmationDB.event_id == event_id)
            users_ids = (await session.execute(query)).scalars().all()
            return list(users_ids)

    async def delete_confirmation_of_event(self, event_id: str) -> bool:
        """
        Deletes all confirmation that are linked to the given event id
        Args:
            event_id: Unique id for every event.

        Returns: Bool if everything was deleted
        """
        try:
            async with self.session() as session:
                await session.execute(delete(ConfirmationDB).where(ConfirmationDB.event_id == event_id))
            self._log_info(f"Deleted all confirmations for event: {event_id}")
            return True
        except SQLAlchemyError:
            return False

    async def create_event(
        self,
        *,
        host: int,
        name: str,
        time: datetime,
        invites: list[discord.User],
        mode: t.Literal["OPEN", "CLOSED", "INVITE_ONLY"],
    ) -> str:
        """
        Creates a new event
        Args:
            host: User id of the host of the event.
            name: Name of the event.
            time: Time when the event happens.
            invites: List of invited Discord users.
            mode: Whether the event is open, closed or invite only

        Returns: The id to identify the event.
        """
        event_id = str(host) + str(datetime.now(tz=SERVER_TZ))
        async with self.session() as session:
            session.add(Events(id=str(event_id), host=int(host), name=str(name), time=time, mode=mode))
            await session.flush()
            for invite in invites:
                session.add(ConfirmationDB(event_id=event_id, user_id=invite.id, confirmation=None, reminders="0"))
        self._log_info(f"Event created {event_id}")
        return event_id

    async def get_event_by_id(self, id: str) -> Event | None:
        """
        Gets an event by an id
        """
        async with self.session() as session:
            event = await session.get(Events, id)
            users = await self.get_confirmations_for_event(event_id=id)
        if event is None:
            self._log_error(f"Event not found by id {id}")
            return None
        return Event(
            id=event.id,
            host=event.host,
            name=event.name,
            time=event.time,
            invites=users,
            mode=event.mode,
        )

    async def get_events(self) -> list[Event]:
        """
        Gets all events
        """
        async with self.session() as session:
            query = select(Events)
            events = (await session.execute(query)).scalars().all()
        result_events = []
        for event in events:
            users = await self.get_confirmations_for_event(event_id=event.id)
            event_data = Event(
                id=event.id,
                host=event.host,
                name=event.name,
                time=event.time,
                invites=users,
                mode=event.mode,
            )
            result_events.append(event_data)
        return result_events

    @staticmethod
    def _apply_event_updates(
        event: Events,
        *,
        host: int | None,
        name: str | None,
        time: datetime | None,
        mode: str | None,
    ) -> None:
        updates = {"host": host, "name": name, "time": time, "mode": mode}
        for field, value in updates.items():
            if value is not None:
                setattr(event, field, value)

    async def update_event(
        self,
        *,
        id: str,
        host: int | None = None,
        name: str | None = None,
        time: datetime | None = None,
        mode: str | None = None,
    ) -> bool:
        """
        Updates an event
        Args:
            id: Unique id for an event.
            host: User id of the host of the event.
            name: Name of the event.
            time: Time when the event happens.
            mode: Whether the event is open, closed or invite only

        Returns: Bool whether update succeeded.
        """
        try:
            async with self.session() as session:
                event = await session.get(Events, id)
                if event is None:
                    return False
                self._apply_event_updates(event, host=host, name=name, time=time, mode=mode)
            self._log_info(f"Event {id} updated")
            return True
        except SQLAlchemyError:
            return False

    async def delete_event(self, id: str) -> bool:
        try:
            async with self.session() as session:
                await session.execute(delete(ConfirmationDB).where(ConfirmationDB.event_id == id))
                await session.execute(delete(Events).where(Events.id == id))
            self._log_info(f"Deleted all confirmations for event: {id}")
            self._log_info(f"Event {id} deleted")
            return True
        except SQLAlchemyError:
            return False
