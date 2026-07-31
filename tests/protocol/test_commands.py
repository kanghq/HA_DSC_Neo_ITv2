"""The ITv2 command enum."""

from __future__ import annotations

from dsc_itv2.commands import ACK_COMMANDS, Command, name_of
import pytest


@pytest.mark.parametrize(
    ("member", "value"),
    [
        ("Simple_Ack", 0),
        ("Command_Error", 1281),
        ("Command_Response", 1282),
        ("Connection_Poll", 1536),
        ("Connection_Open_Session", 1546),
        ("Connection_End_Session", 1547),
        ("Connection_Software_Version", 1549),
        ("Connection_Request_Access", 1550),
        ("Connection_System_Capabilities", 1555),
        ("Configuration_Enter", 1796),
        ("Configuration_Installers_Section_Read", 1825),
        ("Configuration_Installers_Section_Write", 1826),
        ("Configuration_Write_Time_and_Date", 1857),
        ("Configuration_Write_Single_Zone_Bypass_Write", 1866),
        ("ModuleStatus_Zone_Status", 2065),
        ("ModuleStatus_Partition_Status", 2066),
        ("ModuleStatus_System_Trouble_Status_New", 2082),
        ("ModuleControl_Partition_Arm_Control", 2304),
        ("ModuleControl_Partition_Disarm_Control", 2305),
        ("ModuleControl_Activate_FAP", 2312),
        ("Notification_Arming_Disarming", 562),
        ("Notification_Partition_Ready_Status", 569),
        ("Response_Time_and_Date", 18225),
    ],
)
def test_wire_values_are_stable(member, value):
    """These are OEM wire values: changing one breaks interoperability."""
    assert int(getattr(Command, member)) == value


def test_every_command_fits_in_a_uint16():
    assert all(0 <= int(c) <= 0xFFFF for c in Command)


def test_ack_commands_membership():
    assert frozenset(
        {Command.Simple_Ack, Command.Command_Response, Command.Command_Error}
    ) == ACK_COMMANDS


@pytest.mark.parametrize("cmd", [Command.Connection_Poll, Command.ModuleStatus_Zone_Status])
def test_non_ack_commands_are_excluded(cmd):
    assert cmd not in ACK_COMMANDS


def test_name_of_resolves_known_commands():
    assert name_of(0) == "Simple_Ack"
    assert name_of(int(Command.Connection_Poll)) == "Connection_Poll"


def test_name_of_accepts_enum_members():
    assert name_of(Command.Connection_Poll) == "Connection_Poll"


@pytest.mark.parametrize(("value", "expected"), [(0x9999, "Unknown(0x9999)"), (0xFFFF, "Unknown(0xffff)")])
def test_name_of_falls_back_for_unknown_values(value, expected):
    assert name_of(value) == expected


def test_name_of_never_raises():
    for value in (-1, 0, 1, 0x1_0000):
        assert isinstance(name_of(value), str)
