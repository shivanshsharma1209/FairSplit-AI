"""
Category-aware proportional split engine.

Algorithm:
  1. Each item's price is divided evenly among its assigned members, tracked
     both per-member and per-(member, category).
  2. For each ChargeLine on the receipt:
       - If charge.category is None, it's a bill-wide charge (e.g. a flat
         service charge): distribute proportionally to each member's share
         of the WHOLE bill's item subtotal.
       - If charge.category is set (e.g. "Food Tax" scoped to "Food"), it is
         distributed ONLY among members who consumed that category,
         proportionally to their share of THAT category's subtotal. This
         prevents cross-subsidization — someone who ordered no food never
         pays a cent of "Food Tax".
  3. Discounts (charge_type == "discount") are subtracted the same way taxes
     and service charges are added.
  4. All monetary values are rounded to 2 decimals; any residual rounding
     drift is corrected on the largest payer so member totals sum exactly to
     the table total.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from app.models import ChargeShare, MemberBreakdown, SplitRequest, SplitResponse

TWO_PLACES = Decimal("0.01")


def _round2(value) -> float:
    return float(Decimal(str(value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP))


def compute_split(request: SplitRequest) -> SplitResponse:
    receipt = request.receipt_data
    items = receipt.items
    n_items = len(items)

    if not request.members:
        raise ValueError("At least one member is required to split a bill")

    for assignment in request.assignments:
        if assignment.item_index < 0 or assignment.item_index >= n_items:
            raise ValueError(f"Invalid item_index {assignment.item_index}")
        if not assignment.assigned_members:
            raise ValueError(f"Item index {assignment.item_index} has no assigned members")
        unknown = set(assignment.assigned_members) - set(request.members)
        if unknown:
            raise ValueError(f"Unknown member(s) in assignment: {sorted(unknown)}")

    # --- Step 1: raw subtotals, per member and per (member, category) ---
    raw_by_member: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    raw_by_member_category: dict[tuple[str, str], Decimal] = defaultdict(lambda: Decimal("0"))
    raw_by_category: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    assigned_items_by_member: dict[str, list[dict]] = defaultdict(list)

    for assignment in request.assignments:
        item = items[assignment.item_index]
        k = len(assignment.assigned_members)
        item_price = Decimal(str(item.price))
        share = item_price / k

        for member in assignment.assigned_members:
            raw_by_member[member] += share
            raw_by_member_category[(member, item.category)] += share
            raw_by_category[item.category] += share
            assigned_items_by_member[member].append(
                {
                    "item_index": assignment.item_index,
                    "name": item.name,
                    "category": item.category,
                    "share_amount": _round2(share),
                    "split_between": k,
                }
            )

    S = sum(raw_by_member.values(), Decimal("0"))
    if S <= 0:
        raise ValueError("No participant was assigned any items")

    # --- Step 2 & 3: distribute each ChargeLine ---
    # member -> list of ChargeShare, and member -> signed running total from charges
    charge_shares_by_member: dict[str, list[ChargeShare]] = defaultdict(list)
    charge_delta_by_member: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))

    for charge in receipt.charges:
        charge_amount = Decimal(str(charge.amount))
        sign = Decimal("-1") if charge.charge_type == "discount" else Decimal("1")

        if charge.category is None:
            # Bill-wide: proportional to each member's share of the whole bill.
            for member in request.members:
                r_i = (raw_by_member.get(member, Decimal("0")) / S) if S > 0 else Decimal("0")
                member_amount = r_i * charge_amount
                if member_amount == 0:
                    continue
                charge_shares_by_member[member].append(
                    ChargeShare(
                        label=charge.label,
                        charge_type=charge.charge_type,
                        category=None,
                        amount=_round2(sign * member_amount),
                    )
                )
                charge_delta_by_member[member] += sign * member_amount
        else:
            # Category-scoped: proportional only among members who consumed that category.
            category_total = raw_by_category.get(charge.category, Decimal("0"))
            if category_total <= 0:
                # No one is assigned to this category — nothing to distribute against.
                continue
            for member in request.members:
                member_cat_amount = raw_by_member_category.get((member, charge.category), Decimal("0"))
                if member_cat_amount <= 0:
                    continue
                r_i = member_cat_amount / category_total
                member_amount = r_i * charge_amount
                charge_shares_by_member[member].append(
                    ChargeShare(
                        label=charge.label,
                        charge_type=charge.charge_type,
                        category=charge.category,
                        amount=_round2(sign * member_amount),
                    )
                )
                charge_delta_by_member[member] += sign * member_amount

    # --- Step 4: assemble per-member breakdowns ---
    breakdowns: list[MemberBreakdown] = []
    rounded_totals: list[Decimal] = []

    for member in request.members:
        s_i = raw_by_member.get(member, Decimal("0"))
        category_subtotals = {
            category: _round2(amount)
            for (m, category), amount in raw_by_member_category.items()
            if m == member
        }
        total_owed_raw = s_i + charge_delta_by_member.get(member, Decimal("0"))
        rounded_total = Decimal(str(_round2(total_owed_raw)))
        rounded_totals.append(rounded_total)

        breakdowns.append(
            MemberBreakdown(
                member_name=member,
                assigned_items=assigned_items_by_member.get(member, []),
                category_subtotals=category_subtotals,
                charge_shares=charge_shares_by_member.get(member, []),
                individual_subtotal=_round2(s_i),
                total_owed=float(rounded_total),
            )
        )

    # --- Table-level totals + rounding reconciliation ---
    table_subtotal = Decimal(str(_round2(S)))
    total_tax_and_service = sum(
        (Decimal(str(c.amount)) for c in receipt.charges if c.charge_type != "discount"),
        Decimal("0"),
    )
    total_discount = sum(
        (Decimal(str(c.amount)) for c in receipt.charges if c.charge_type == "discount"),
        Decimal("0"),
    )
    table_total_raw = S + total_tax_and_service - total_discount
    table_total = Decimal(str(_round2(table_total_raw)))

    sum_of_rounded = sum(rounded_totals, Decimal("0"))
    drift = table_total - sum_of_rounded
    if drift != 0 and breakdowns:
        largest = max(breakdowns, key=lambda b: b.total_owed)
        largest.total_owed = _round2(largest.total_owed + float(drift))

    reconciliation_difference = _round2(Decimal(str(receipt.printed_total)) - table_total)

    return SplitResponse(
        member_breakdowns=breakdowns,
        table_subtotal=float(table_subtotal),
        table_total=float(table_total),
        reconciliation_difference=reconciliation_difference,
        currency=receipt.currency,
    )