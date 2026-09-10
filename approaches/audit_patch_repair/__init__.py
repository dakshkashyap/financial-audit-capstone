"""AuditPatch V0 — detect → minimal numerical patch → revalidate → certificate."""

from .pipeline import repair_item, RepairResult

__all__ = ["repair_item", "RepairResult"]
