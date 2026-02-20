"""Import all models so they are registered with Base.metadata."""

from app.database.models.member import Member, MemberStatusHistory
from app.database.models.settings import AppSettings
from app.database.models.audit_log import AuditLog
from app.database.models.membership_fee import MembershipFeePeriod, MembershipFeePayment
from app.database.models.target_fee import TargetFeeCampaign, TargetFeePayment, TargetFeeDocument
from app.database.models.electricity import (
    ElectricityTariff, MeterReading, ElectricityPayment, SntMeterReading
)
from app.database.models.note import Note
from app.database.models.custom_tab import CustomTab, CustomColumn, CustomRow, CustomCellValue

__all__ = [
    "Member", "MemberStatusHistory",
    "AppSettings",
    "AuditLog",
    "MembershipFeePeriod", "MembershipFeePayment",
    "TargetFeeCampaign", "TargetFeePayment", "TargetFeeDocument",
    "ElectricityTariff", "MeterReading", "ElectricityPayment", "SntMeterReading",
    "Note",
    "CustomTab", "CustomColumn", "CustomRow", "CustomCellValue",
]
