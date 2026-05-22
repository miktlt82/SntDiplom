"""Enumerations and status constants."""

import enum


class MemberStatus(str, enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class PaymentStatus(str, enum.Enum):
    NOT_PAID = "not_paid"
    PARTIAL = "partial"
    PAID = "paid"
    OVERPAID = "overpaid"


class TargetFeeType(str, enum.Enum):
    PER_SOTKA = "per_sotka"
    FIXED = "fixed"


class AuditAction(str, enum.Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    ARCHIVE = "archive"
    RESTORE = "restore"
    PAYMENT = "payment"
    IMPORT = "import"
    EXPORT = "export"
    BACKUP = "backup"
