import datetime as dt
from dataclasses import dataclass, field
from enum import IntEnum

from ..client import ConfigClient


class TriggerType(IntEnum):
    """Type of the event that triggered a task, as recorded in the trigger history."""

    BUTTON_UP = 0
    BUTTON_DOWN = 1
    BUTTON_HOLD = 2
    TIMER = 3
    DATA = 4
    POSITION = 5
    IN_RANGE = 6
    OUT_OF_RANGE = 7
    TEMPERATURE = 8
    DAY_MODE = 9
    FAN_MODE = 10
    OPERATION_MODE = 11
    CONNECT = 12
    DISCONNECT = 13
    BOOT = 14
    LEARN = 15
    TAP = 16

    # A module's alert, eg. when it loses a line feed, with the feed number in param1
    MODULE_ALERT = 0xA004


@dataclass
class EventLogEntry:
    """A trigger history entry: a source object starting a task."""

    time_stamp: str | None = field(default=None, metadata={"name": "TimeStamp"})
    source: int | None = field(default=None, metadata={"name": "Source"})
    destination: int | None = field(default=None, metadata={"name": "Destination"})
    event: int | None = field(default=None, metadata={"name": "Event"})
    param1: int | None = field(default=None, metadata={"name": "Param1"})
    param2: int | None = field(default=None, metadata={"name": "Param2"})

    # Only set by GetEventLogNext, -1 marks the last entry
    position: int | None = field(default=None, metadata={"name": "Position"})

    @property
    def timestamp(self) -> dt.datetime | None:
        """The time of the entry, in the controller's local time."""
        if self.time_stamp is None:
            return None

        return dt.datetime.fromisoformat(self.time_stamp)

    @property
    def trigger_type(self) -> TriggerType | None:
        """The type of the trigger, if known."""
        try:
            return TriggerType(self.event)  # type: ignore[arg-type]
        except ValueError:
            return None


class SysLogType(IntEnum):
    """Type of a system log entry.

    In the order of the levels accepted by the Host Command "LOG" command.
    """

    DEBUG = 0
    DUMP = 1
    INFORMATION = 2
    WARNING = 3
    ERROR = 4
    FATAL = 5
    TASK = 6
    DEVICE = 7
    QUERY = 8
    PROF = 9


@dataclass
class SysLogEntry:
    """A system log entry."""

    type: int | None = field(default=None, metadata={"name": "Type"})
    # Month, day and time only, eg. "01-02T03:04:05"
    time: str | None = field(default=None, metadata={"name": "Time"})
    src: str | None = field(default=None, metadata={"name": "Src"})
    msg: str | None = field(default=None, metadata={"name": "Msg"})

    @property
    def log_type(self) -> SysLogType | None:
        """The type of the entry, if known."""
        try:
            return SysLogType(self.type)  # type: ignore[arg-type]
        except ValueError:
            return None


@dataclass
class ModuleInfo:
    """Status of a module on an enclosure's bus."""

    @dataclass
    class Status:
        proc0: str | None = field(default=None, metadata={"name": "Proc0"})
        proc1: str | None = field(default=None, metadata={"name": "Proc1"})

    address: int | None = field(default=None, metadata={"name": "Address"})
    vid: int | None = field(default=None, metadata={"name": "VID"})
    revision: int | None = field(default=None, metadata={"name": "Revision"})
    type: int | None = field(default=None, metadata={"name": "Type"})
    version: str | None = field(default=None, metadata={"name": "Version"})
    status: Status | None = field(default=None, metadata={"name": "Status"})
    errors: int | None = field(default=None, metadata={"name": "Errors"})
    model: str | None = field(default=None, metadata={"name": "Model"})


@dataclass
class NoParams:
    pass


@dataclass
class GetEventLog:
    # The controller only answers when an (empty) call element is sent
    call: NoParams | None = field(
        default=None, metadata={"name": "call", "type": "Element"}
    )
    result: list[EventLogEntry] | None = field(
        default_factory=list[EventLogEntry],
        metadata={"wrapper": "return", "name": "Entry", "type": "Element"},
    )


@dataclass
class GetEventLogNext:
    call: int | None = field(default=None, metadata={"name": "call", "type": "Element"})
    result: EventLogEntry | None = field(default=None, metadata={"name": "return"})


@dataclass
class GetSysLog:
    # The controller only answers when an (empty) call element is sent
    call: NoParams | None = field(
        default=None, metadata={"name": "call", "type": "Element"}
    )
    result: list[SysLogEntry] | None = field(
        default_factory=list[SysLogEntry],
        metadata={"wrapper": "return", "name": "Entry", "type": "Element"},
    )


@dataclass
class GetModules:
    call: int | None = field(default=None, metadata={"name": "call", "type": "Element"})
    result: list[ModuleInfo] | None = field(
        default_factory=list[ModuleInfo],
        metadata={"wrapper": "return", "name": "Module", "type": "Element"},
    )


@dataclass(kw_only=True)
class IDiagnostic:
    get_event_log: GetEventLog | None = None
    get_event_log_next: GetEventLogNext | None = None
    get_sys_log: GetSysLog | None = None
    get_modules: GetModules | None = None


class DiagnosticInterface:
    """Wrapper for the `IDiagnostic` RPC interface.

    This is the interface InFusion Diagnostics uses for its "History" (trigger
    history) and "Log" (system log) views. Only read-only methods are wrapped.
    """

    @staticmethod
    async def get_event_log(
        client: ConfigClient, master: int | None = None
    ) -> list[EventLogEntry]:
        """Get the trigger history, oldest entry first.

        Each entry records an object (a button, timer, sensor, etc.) starting a task.

        Args:
            client: A config client instance
            master: The master number to address, defaults to the connected master

        Returns:
            A list of trigger history entries.
        """
        return await client.rpc(IDiagnostic, GetEventLog, NoParams(), master=master)

    @staticmethod
    async def get_event_log_next(
        client: ConfigClient, position: int, master: int | None = None
    ) -> EventLogEntry | None:
        """Get a single trigger history entry by position.

        Positions count from 0 at the oldest entry held, so polling from the length
        of the history returns new entries as they are recorded. How many entries
        the controller keeps, and what it drops once full, is not known, so check
        the timestamps of polled entries rather than relying on positions alone.

        Args:
            client: A config client instance
            position: The position of the entry to fetch
            master: The master number to address, defaults to the connected master

        Returns:
            The entry, or None if there is no entry at this position yet.
        """
        entry = await client.rpc(IDiagnostic, GetEventLogNext, position, master=master)

        # Positions past the end return an empty entry
        return entry if entry.time_stamp is not None else None

    @staticmethod
    async def get_sys_log(
        client: ConfigClient, master: int | None = None
    ) -> list[SysLogEntry]:
        """Get the system log, oldest entry first.

        Args:
            client: A config client instance
            master: The master number to address, defaults to the connected master

        Returns:
            A list of system log entries.
        """
        return await client.rpc(IDiagnostic, GetSysLog, NoParams(), master=master)

    @staticmethod
    async def get_modules(
        client: ConfigClient, enclosure: int = 1, master: int | None = None
    ) -> list[ModuleInfo]:
        """Get the status of the modules that respond on an enclosure's bus.

        Args:
            client: A config client instance
            enclosure: The enclosure number, 1 on a single enclosure system
            master: The master number to address, defaults to the connected master

        Returns:
            A list of module status objects.
        """
        return await client.rpc(IDiagnostic, GetModules, enclosure, master=master)
