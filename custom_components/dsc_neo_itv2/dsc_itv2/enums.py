"""ITv2 enumerations.

All byte/ushort enums used by message bodies. Sourced verbatim from
NeoHub ``TLink/ITv2/Enumerations/*.cs`` (GPL-3.0).
"""
from __future__ import annotations

from enum import IntEnum, IntFlag


class ArmingMode(IntEnum):
    Disarm = 0
    StayArm = 1
    AwayArm = 2
    ArmWithNoEntryDelay = 3
    NightArm = 4
    QuickArm = 5
    UserArm = 6
    StayArmWithNoEntryDelay = 7
    AwayArmWithNoEntryDelay = 8
    NightArmWithNoEntryDelay = 9
    GlobalStayArm = 11
    GlobalAwayArm = 12
    CustomizedArmingModeA = 13
    CustomizedArmingModeB = 14
    CustomizedArmingModeC = 15
    CustomizedArmingModeD = 16
    InstantStayArm = 17
    ArmingHidden = 18
    Unknown = 255


class ProgrammingMode(IntEnum):
    InstallersProgramming = 0
    AccessCodeProgramming = 1
    UserFunctionProgramming = 2
    UserBypassProgramming = 3


class BypassStatus(IntEnum):
    NotBypassed = 0
    Bypassed = 1


class CommandResponseCode(IntEnum):
    """Per NeoHub ``CommandResponseCode``. 0 = Success; others map to NACK strings.

    Only the well-known codes are listed; the panel may return other byte
    values for vendor-specific conditions: keep numeric values intact.
    """
    Success = 0
    CannotExitConfiguration = 1
    InvalidProgrammingType = 2
    UnsupportedModule = 3
    InvalidSignalType = 4
    NotInCorrectProgrammingMode = 16
    InvalidAccessCode = 17
    AccessCodeRequired = 18
    SystemPartitionBusy = 19
    InvalidPartition = 20
    FunctionNotAvailable = 23
    InternalError = 24
    CommandTimeOut = 25
    NoTroublesPresentForRequestedType = 26
    NoRequestedAlarmsFound = 27
    InvalidDeviceModule = 28
    InvalidTroubleType = 29


class ITv2NackCode(IntEnum):
    """NACK reasons attached to Command_Error (per NeoHub ``ITv2NackCode``)."""
    UnknownError = 0
    InvalidCommandLength = 1
    InvalidCommand = 2
    InvalidSequence = 3
    PanelNotResponding = 4
    InvalidPassthruCommand = 5
    InvalidDestination = 6
    InvalidSession = 7
    InsufficientBufferSize = 8
    LockOut = 9
    UnsupportedSubCommand = 10
    PowerupShunt = 11
    InvalidProgrammingMode = 16
    InvalidAccessCode = 17
    AccessCodeRequired = 18
    SystemBusy = 19
    InvalidPartition = 20
    FunctionNotAvailable = 23
    InternalError = 24
    CommandTimeout = 25
    InvalidDeviceModule = 28
    InvalidTroubleType = 29
    ProgTagOrAccessCodeRequired = 30
    ProgTagRequired = 31


class PanelDeviceType(IntEnum):
    Unknown = 0xFF
    DscInterfaceCommunicatorModule = 0x02
    Icontrol = 0x80
    KeyPad = 0x81
    GenericThirdpartyDevice = 0x8F


class ProtocolCompatibility(IntEnum):
    Unknown = 0
    v129 = 0x0129
    v202 = 0x0202
    v223 = 0x0223


class ZoneStatusFlags(IntFlag):
    """ModuleStatus_Zone_Status per-zone byte flags."""
    Secure = 0x00
    Open = 0x01
    Tamper = 0x02
    Fault = 0x04
    LowBattery = 0x08
    Delinquency = 0x10
    Alarm = 0x20
    AlarmMemory = 0x40
    Bypass = 0x80


class PartitionStatus1(IntFlag):
    """ModulePartitionStatus first status byte. Mixed-mode (values vs bits).

    .. note:: This is a packed enum (the panel sets a state value, not OR'd flags),
       but the high bits are independent flags (ExitDelay/EntryDelay/QuickExit).
    """
    Armed = 0x01
    ReadyToArm = 0x02
    StayArmed = 0x03
    ReadyToForceArm = 0x04
    ArmedAway = 0x05
    NotReadyToArm = 0x08
    NightArmed = 0x09
    WalkTestMode = 0x10
    ArmedWithNoEntryDelay = 0x11
    ExitDelayInProgress = 0x20
    EntryDelayInProgress = 0x40
    QuickExitInProgress = 0x80


class PartitionStatus2(IntFlag):
    PartitionInAlarm = 0x01
    TroublesPresent = 0x02
    ZonesBypassed = 0x04
    InProgrammingMode = 0x08
    AlarmsInMemory = 0x10
    DoorChimeEnabled = 0x20
    AudibleBellSiren = 0x40
    AudibleKeypadBuzzerAlarm = 0x80


class PartitionStatus3(IntFlag):
    FirePreAlertInProgress = 0x01


class ExitDelayFlags(IntFlag):
    AudibleExitDelay = 0x01
    ExitDelayHasRestarted = 0x02
    ExitDelayUrgency = 0x04
    ExitDelayActive = 0x80


class LifestyleZoneStatus(IntEnum):
    Restored = 0
    Open = 1
    Unknown = 0xFF


class PartitionReadyStatus(IntEnum):
    Reserved = 0
    ReadyToArm = 1
    ReadyToForceArm = 2
    NotReadyToArm = 3


class ArmDisarmMethod(IntEnum):
    Unknown = 0
    AccessCode = 1
    FunctionKey = 2


class LabelCollection(IntEnum):
    """NotificationLabelText collection identifier (one-byte sentinel)."""
    Zone = 0xD1
    Partition = 0xD3
    User = 0xD9


class ReadWriteAccess(IntEnum):
    ReadOnly = 0
    ReadWrite = 1


class ProgrammingLeadInOutType(IntEnum):
    LeadIn = 0
    LeadOut = 1


class ProgrammingLeadInOutAccess(IntEnum):
    ConfigurationThroughInteractiveServices = 0
    ForFutureUse = 1
    ConfigurationThroughKeypad = 2
    Dls = 3
    C24 = 4


class NotificationAccessCodeParameter(IntFlag):
    AccessCode = 1
    Attributes = 2
    PartitionAssignment = 4
    Label = 8


class PanelUserAttributes(IntFlag):
    """User attribute flags (one byte per user)."""
    NoneFlag = 0x00
    Supervisor = 0x01
    DuressCode = 0x02
    CanBypassZone = 0x04
    RemoteAccess = 0x08
    BellSquawk = 0x40
    OneTimeUse = 0x80


class UserCodeType(IntEnum):
    NoneCode = 0x00
    Pin = 0x01
    ProximityTag = 0x02
