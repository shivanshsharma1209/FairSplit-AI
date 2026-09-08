"""
Pydantic v2 schemas: receipt structure (with category-scoped charges),
split requests, and split results.
"""
from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

ChargeType = Literal["tax", "service_charge", "discount"]


class LineItem(BaseModel):
    """A single line item extracted from a receipt."""

    name: str
    category: str = Field(
        default="Uncategorized",
        description="e.g. 'Food', 'Beverage', 'Service' — used to scope category-specific charges",
    )
    quantity: int = 1
    price: float = Field(..., description="Total price for this line (already includes quantity)")
    confidence: float = Field(..., ge=0.0, le=1.0)


class ChargeLine(BaseModel):
    """
    A single distinct tax, service charge, or discount line as printed on
    the receipt. Never lumped together — e.g. 'Food Tax' and 'Beverage Tax'
    are two separate ChargeLine entries, each scoped to their own category.
    """

    label: str = Field(..., description="e.g. 'Food Taxable VAT', 'Service Tax', 'Loyalty Discount'")
    charge_type: ChargeType
    category: Optional[str] = Field(
        default=None,
        description="If set, this charge applies only to items of this category. "
        "If None, it applies proportionally across the whole bill.",
    )
    amount: float = Field(..., ge=0.0, description="Always a positive magnitude; sign is implied by charge_type")


class ReceiptData(BaseModel):
    """Full parsed receipt, including category-scoped charges and validation metadata."""

    items: List[LineItem]
    charges: List[ChargeLine] = Field(default_factory=list)
    subtotal: float
    printed_total: float
    currency: str = Field(default="USD", description="ISO 4217 code, e.g. USD, INR, EUR")
    math_is_valid: bool
    math_notes: Optional[str] = None


class ItemAssignment(BaseModel):
    """Maps a receipt line item to the members splitting it (equal split among them)."""

    item_index: int
    assigned_members: List[str]


class SplitRequest(BaseModel):
    """Request payload for computing a bill split."""

    receipt_data: ReceiptData
    members: List[str]
    assignments: List[ItemAssignment]


class ChargeShare(BaseModel):
    """One member's share of a single ChargeLine."""

    label: str
    charge_type: ChargeType
    category: Optional[str] = None
    amount: float


class MemberBreakdown(BaseModel):
    """Computed monetary breakdown for a single member."""

    member_name: str
    assigned_items: List[dict]
    category_subtotals: Dict[str, float] = Field(
        default_factory=dict, description="This member's raw item subtotal per category"
    )
    charge_shares: List[ChargeShare] = Field(default_factory=list)
    individual_subtotal: float
    total_owed: float


class SplitResponse(BaseModel):
    """Final split result across all members."""

    member_breakdowns: List[MemberBreakdown]
    table_subtotal: float
    table_total: float
    reconciliation_difference: float
    currency: str = Field(default="INR", description="ISO 4217 code, e.g. USD, INR, EUR")