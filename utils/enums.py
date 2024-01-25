from enum import Enum, auto


class SettingsEnum(Enum):
    """
    An enum class for the database and the settings command.
    Naming convention:
        Roles: [Any] Role
        Channel: [Any] Channel
    else the "extensions/administration/settings.py" won't recognize it
    """

    TeamRole = "Team Role"
    VerifiedRole = "Verified Role"
    ModLogChannel = "Mod Log Channel"
    ModmailChannel = "Modmail Channel"
    VerificationChannel = "Verification Channel"
    Join2CreateChannel = "Join2Create Channel"
    AuditLogChannel = "Audit-Log Channel"
