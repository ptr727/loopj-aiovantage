"""Event classes for Vantage controller events."""

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

T = TypeVar("T")

__all__ = [
    "Connected",
    "Disconnected",
    "Reconnected",
    "StatusReceived",
    "EnhancedLogReceived",
    "TriggerReceived",
    "SystemLogReceived",
    "ObjectAdded",
    "ObjectUpdated",
    "ObjectDeleted",
]


class EventDispatcher:
    """Simple event dispatcher that allows subscription to and emission of events."""

    def __init__(self) -> None:
        """Initialize the event dispatcher."""
        self._subscribers: dict[type, list[Callable[[Any], None]]] = defaultdict(list)

    def subscribe(
        self, event_type: type[T], callback: Callable[[T], None]
    ) -> Callable[[], None]:
        """Register a callback function to be called when an event is emitted.

        Args:
            event_type: Event type to subscribe to.
            callback: Callback function to call when an event of this type is emitted.

        Returns:
            A function that can be called to unsubscribe from the event.
        """
        self._subscribers[event_type].append(callback)

        def unsubscribe() -> None:
            self._subscribers[event_type].remove(callback)
            if not self._subscribers[event_type]:
                del self._subscribers[event_type]

        return unsubscribe

    def emit(self, event: Any) -> None:
        """Emit an event, notifying all subscribers.

        Args:
            event: The event to emit.
        """
        event_type = type(event)  # type: ignore
        if event_type in self._subscribers:
            for callback in self._subscribers[event_type]:
                callback(event)


class Connected:
    """Event emitted when a client connection is established."""


class Disconnected:
    """Event emitted when the client connection is lost."""


class Reconnected:
    """Event emitted when the client connection is re-established."""


@dataclass
class StatusReceived:
    """Event emitted when a "S:" status is received."""

    category: str
    """The status category, eg. "LOAD", "BLIND", etc."""

    vid: int
    """The unique Vantage ID of the object the status applies to."""

    args: list[str]
    """The arguments of the status message."""


@dataclass
class EnhancedLogReceived:
    """Event emitted when an "EL:" enhanced log is received."""

    log: str
    """The enhanced log message."""


@dataclass
class TriggerReceived:
    """Event emitted when an object triggers a task, from the "EVENT" enhanced log."""

    source: int
    """The VID of the object that fired, eg. a button, timer or sensor."""

    destination: int
    """The VID of the task that was started."""

    event: int
    """The type of the trigger, see `aiovantage.config_client.TriggerType`."""

    param1: int
    """The first trigger parameter."""

    param2: int
    """The second trigger parameter."""

    @classmethod
    def parse(cls, log: str) -> "TriggerReceived | None":
        """Parse an "EVENT" enhanced log of the form "<src> <dst> <event> <p1> <p2>".

        Returns:
            The trigger, or None if the log is not a trigger log.
        """
        tokens = log.split()
        if len(tokens) != 5:
            return None

        try:
            return cls(*(int(token) for token in tokens))
        except ValueError:
            return None


@dataclass
class SystemLogReceived:
    """Event emitted when a system log is received, from the "SYSTEM" enhanced log."""

    type: int
    """The type of the log, see `aiovantage.config_client.SysLogType`."""

    source: str
    """The source of the log, eg. "Controller"."""

    message: str
    """The log message."""

    @classmethod
    def parse(cls, log: str) -> "SystemLogReceived | None":
        """Parse a "SYSTEM" enhanced log of the form "<type> <source> <message>".

        Returns:
            The system log, or None if the log is not a system log.
        """
        log_type, _, rest = log.partition(" ")
        source, _, message = rest.partition(" ")

        # Object status logs carry an "Interface.Method", and triggers are numeric
        if not log_type.isdigit() or not source or "." in source or source.isdigit():
            return None

        return cls(int(log_type), source, message.strip())


@dataclass
class ObjectAdded(Generic[T]):
    """Event emitted when an object is added to a controller."""

    obj: T
    """The object that the event is related to."""


@dataclass
class ObjectUpdated(Generic[T]):
    """Event emitted when an object is updated."""

    obj: T
    """The object that the event is related to."""

    attrs_changed: list[str]
    """A list of attributes that have changed."""


@dataclass
class ObjectDeleted(Generic[T]):
    """Event emitted when an object is removed from a controller."""

    obj: T
    """The object that the event is related to."""
