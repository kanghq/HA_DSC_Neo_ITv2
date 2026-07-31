"""DSC ITv2 command catalog.

OEM-authoritative: extracted verbatim from
`Tyco.TSP.Communications.TLink.dll` (`ITV2Command` enum, 170 entries),
plus 1 community-contributed entry from NeoHub (marked below).

Source of truth: `Tyco.TSP.Communications.ITV2.ITV2Command`. Cross-ref:
NeoHub `DSC.TLink.ITv2.Enumerations.ITv2Command` (GPL-3.0,
BrianHumlicek/NeoHub): confirms 0x0250 in real panel traffic.
"""

from __future__ import annotations

from enum import IntEnum


class Command(IntEnum):
    """ITv2 protocol command IDs (16-bit, big-endian on wire).

    Names match `Tyco.TSP.Communications.ITV2.ITV2Command` exactly so they
    can be cross-referenced against decompiled DLS5 source.
    """

    # --- Acknowledgements (1281-1282) ---
    Command_Error = 1281
    Command_Response = 1282

    # --- Simple ack (0) ---
    Simple_Ack = 0

    # --- Logging (256-274) ---
    Logging_Get_Event_Buffer_information = 256
    Logging_Event_Buffer_Read_by_Event_Number = 257
    Logging_Single_Event_Buffer_Read = 258
    Logging_SMS_Preview_Read = 259
    Logging_Single_SMS_Text_Read = 260
    Logging_Delete_SMS = 261
    Logging_Event_Buffer_Read_by_Date_Time_Stamp = 262
    Logging_Panel_Event_Buffer_Notification = 272
    Logging_Unread_SMS_Notification = 273
    Logging_Panel_Communicable_Event_Tx_Notification = 274

    # --- Notifications (512-752): live broadcasts from panel ---
    Notification_Any_Life_Safety_Communicable_Event = 512
    Notification_Text = 513
    Notification_Life_Style_Zone_Status = 528
    Notification_Time_Date_Broadcast = 544
    Notification_Temperature_Broadcast = 545
    Notification_Command_Output_Activation_Deprecated = 546
    Notification_Chime_Broadcast = 547
    Notification_Panel_Display_Configuration = 548
    Notification_Exit_Delay = 560
    Notification_Entry_Delay = 561
    Notification_Arming_Disarming = 562
    Notification_Arming_PreAlert = 563
    Notification_Enrolment_Status = 564
    Notification_General_Activity_Deprecated = 565
    Notification_Access_Code_Length = 566
    Notification_Partition_Buzzer_Type_Deprecated = 567
    Notification_Partition_Quick_Exit = 568
    Notification_Partition_Ready_Status = 569
    Notification_System_Test = 570
    Notification_Partition_Audible_Bell = 571
    Notification_Partition_Alarm_Memory = 572
    Notification_Miscellaneous_PreAlert = 573
    Notification_Partition_Blank_Status = 574
    Notification_Partition_Trouble_Status = 575
    Notification_Partition_Bypass_Status = 576
    Notification_Partition_Busy_Status = 577
    Notification_Partition_Based_General_Activity = 578
    Notification_Signal_Strength = 579
    Notification_Command_Output_Activation_Extended = 580
    Notification_Partition_Banner_Notification = 581
    Notification_Partition_Buzzer_Type_Extended = 582
    Notification_Access_Code_Update = 592  # 0x0250. NeoHub only; not in DLS5 enum
    Notification_Buffer_Overload = 752

    # --- Firmware upgrade (768-774) ---
    Upgrade_Firmware_Available = 768
    Upgrade_Start_Download = 769
    Upgrade_Cancel_Download = 770
    Upgrade_Download_Complete = 771
    Upgrade_Firmware_Data_Packet = 772
    Upgrade_Firmware_Available_Critical = 773
    Upgrade_Firmware_Update_Status_Notification = 774

    # --- Access level (1024-1026) ---
    AccessLevel_Enter = 1024
    AccessLevel_Exit = 1025
    AccessLevel_Lead_InOut = 1026

    # --- Connection management (1536-1571) ---
    Connection_Poll = 1536
    Connection_Open_Session = 1546
    Connection_End_Session = 1547   # Note: DLS5 enum says "End_session" (lowercase 's')
    Connection_Inform_TX_and_RX_buffer_sizes = 1548
    Connection_Software_Version = 1549
    Connection_Request_Access = 1550
    Connection_Pass_Through_ITv2_Command = 1554
    Connection_System_Capabilities = 1555
    Connection_Panel_Status = 1556
    Connection_Device_Enrolment = 1557
    Connection_Encapsulated_Command_for_Long_Packets = 1570
    Connection_Encapsulated_Command_for_Multiple_Packets = 1571

    # --- Configuration: enter/exit (1792-1796) ---
    Configuration_Enter_Deprecated = 1792
    Configuration_Exit = 1793
    Configuration_Panel_Programming_Lead_InOut = 1794
    Configuration_Access_Code_Wrapper = 1795
    Configuration_Enter = 1796

    # --- Configuration: installer section R/W (1825-1826) ---
    Configuration_Installers_Section_Read = 1825
    Configuration_Installers_Section_Write = 1826

    # --- Configuration: reads (1841-1854) ---
    Configuration_Read_Time_and_Date = 1841
    Configuration_Read_Late_To_Open = 1842
    Configuration_Read_Late_To_Open_Time = 1843
    Configuration_Read_Voice_dialler = 1844
    Configuration_Read_Bypass_Zone = 1845
    Configuration_Read_Access_Code = 1846
    Configuration_Read_Access_Code_Attribute = 1847
    Configuration_Read_Access_Code_Partition_Assignment = 1848
    Configuration_Read_Auto_Arm_Time = 1849
    Configuration_Read_User_Code_Configuration = 1852
    Configuration_Read_Late_To_Open_Time_Single_Day = 1853
    Configuration_Read_Auto_Arm_Time_Read_Single_Day = 1854

    # --- Configuration: writes (1857-1872) ---
    Configuration_Write_Time_and_Date = 1857
    Configuration_Write_Late_To_Open = 1858
    Configuration_Write_Late_To_Open_Time = 1859
    Configuration_Write_Voice_dialler = 1860
    Configuration_Write_Bypass_Zone = 1861
    Configuration_Write_Access_Code = 1862
    Configuration_Write_Access_Code_Attribute = 1863
    Configuration_Write_Access_Code_Partition_Assignment = 1864
    Configuration_Write_Auto_Arm_Time_Program = 1865
    Configuration_Write_Single_Zone_Bypass_Write = 1866
    Configuration_Write_Group_Bypass = 1867
    Configuration_Write_Proximity_Tag_Programming = 1868
    Configuration_Write_Late_To_Open_Time_Single_Day = 1869
    Configuration_Write_Auto_Arm_Time_Program_Single_Day = 1870
    Configuration_Write_Reset_Programming_to_Factory_Default = 1871
    Configuration_Write_Access_Codes_Label = 1872

    # --- Configuration: event reporting (1889-1908) ---
    Configuration_Read_Event_Reporting_Configuration = 1889
    Configuration_Write_Event_Reporting_Configuration = 1890
    Configuration_Notification_Zone_Assignment_Configuration = 1904
    Configuration_Notification_Configuration = 1905
    Configuration_Notification_Partition_Assignment = 1906
    Configuration_Notification_Virtual_Zone_to_Zone_Assignment = 1907
    Configuration_Notification_Configuration_Extend = 1908

    # --- Module status (2048-2114): polled status snapshots ---
    ModuleStatus_Command_Request = 2048
    ModuleStatus_Global_Status = 2064
    ModuleStatus_Zone_Status = 2065
    ModuleStatus_Partition_Status = 2066
    ModuleStatus_Zone_Bypass_Status = 2067
    ModuleStatus_System_Trouble_Status_Deprecated = 2068
    ModuleStatus_Alarm_Memory_Information = 2069
    ModuleStatus_Bus_Status = 2070
    ModuleStatus_Trouble_Detail = 2071
    ModuleStatus_Door_Chime_Status = 2073
    ModuleStatus_Single_Zone_Bypass_Status = 2080
    ModuleStatus_Grouped_Trouble_Status_Deprecated = 2081
    ModuleStatus_System_Trouble_Status_New = 2082
    ModuleStatus_Trouble_Detail_Notification = 2083
    ModuleStatus_Zone_Alarm_Status = 2112
    ModuleStatus_Miscellaneous_NonZone_Alarm_Status = 2113
    ModuleStatus_Diagnostic_Status = 2114

    # --- Module control (2304-2327): commands receiver sends to panel ---
    ModuleControl_Partition_Arm_Control = 2304
    ModuleControl_Partition_Disarm_Control = 2305
    ModuleControl_Command_Output = 2306
    ModuleControl_System_Testing_Deprecated = 2307
    ModuleControl_Door_Chime_Status_Write_Deprecated = 2308
    ModuleControl_Enable_DLS_Window = 2309
    ModuleControl_User_Callup = 2310
    ModuleControl_Auto_Arm_EnableDisable = 2311
    ModuleControl_Activate_FAP = 2312
    ModuleControl_Initiate_Label_Broadcast = 2313
    ModuleControl_Partition_Quick_Exit = 2320
    ModuleControl_Silence_Troubles_Deprecated = 2321
    ModuleControl_User_Activity = 2322
    ModuleControl_Partition_Banner_Display = 2323
    ModuleControl_Partition_Buzzer_Control = 2324
    ModuleControl_Virtual_Zone_Control = 2325
    ModuleControl_Set_Partition_Mode = 2326
    ModuleControl_Door_Chime_Status_Write_Extended = 2327

    # --- Image transfer (3074-3075) ---
    ImageTransfer_Image_File_Header_Command = 3074
    ImageTransfer_File_Transfer_Data_Blocks = 3075

    # --- Virtual keypad (3840-3844) ---
    VirtualKeypad_Control = 3840
    VirtualKeypad_Notification_Key_Pressed = 3841
    VirtualKeypad_Notification_LCD_Update = 3842
    VirtualKeypad_Notification_LCD_Cursor = 3843
    VirtualKeypad_Notification_LED_Status = 3844

    # --- Responses (16640+): replies to specific requests ---
    Response_Get_Event_Buffer_Information = 16640
    Response_Event_Buffer_Read_By_Event_Number = 16641
    Response_Single_Event_Buffer_Read = 16642
    Response_SMS_Preview_Read = 16643
    Response_Single_SMS_Text_Read = 16644
    # Note: DLS5 enum has Response_Event_Buffer_Read_By_Date_Time_Stamp = 16641
    # (same value as Response_Event_Buffer_Read_By_Event_Number. Aliased)

    Response_Installers_Section_Read = 18209
    Response_Time_and_Date = 18225
    Response_Late_To_Open = 18226
    Response_Late_To_Open_Time = 18227
    Response_Voice_Dialler = 18228
    Response_Bypass_Zone = 18229
    Response_Access_Code = 18230
    Response_Access_Code_Attribute = 18231
    Response_Access_Code_Partition_Assignment = 18232
    Response_Auto_Arm_Time = 18233
    Response_User_Code_Configuration = 18236
    Response_Late_To_Open_Time_Single_Day = 18237
    Response_Auto_Arm_Time_Read_Single_Day = 18238
    Response_Event_Reporting_Configuration_Read = 18273


# Convenience: ack-style commands that don't carry an application-layer body
ACK_COMMANDS = frozenset({
    Command.Simple_Ack,
    Command.Command_Response,
    Command.Command_Error,
})


def name_of(value: int) -> str:
    """Return the OEM name for a command ID, or `Unknown(<n>)` if not in enum."""
    try:
        return Command(value).name
    except ValueError:
        return f"Unknown(0x{value:04x})"
