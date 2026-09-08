import pytest

from app.models import ItemAssignment, LineItem, ReceiptData, SplitRequest
from app.services.splitter import compute_split


def make_receipt():
    return ReceiptData(
        items=[
            LineItem(name="Pizza", quantity=1, price=20.00, confidence=0.98),
            LineItem(name="Soda", quantity=1, price=5.00, confidence=0.95),
        ],
        subtotal=25.00,
        tax=2.50,
        service_charge=5.00,
        discount=0.00,
        printed_total=32.50,
        math_is_valid=True,
        math_notes=None,
    )


def test_shared_item_split_evenly():
    receipt = make_receipt()
    request = SplitRequest(
        receipt_data=receipt,
        members=["Alice", "Bob"],
        assignments=[
            ItemAssignment(item_index=0, assigned_members=["Alice", "Bob"]),  # Pizza shared
            ItemAssignment(item_index=1, assigned_members=["Alice"]),        # Soda solo
        ],
    )
    result = compute_split(request)

    alice = next(m for m in result.member_breakdowns if m.member_name == "Alice")
    bob = next(m for m in result.member_breakdowns if m.member_name == "Bob")

    # Alice: half of Pizza (10) + all of Soda (5) = 15
    # Bob: half of Pizza (10) = 10
    assert alice.individual_subtotal == 15.00
    assert bob.individual_subtotal == 10.00


def test_tax_and_service_charge_are_proportional():
    receipt = make_receipt()
    request = SplitRequest(
        receipt_data=receipt,
        members=["Alice", "Bob"],
        assignments=[
            ItemAssignment(item_index=0, assigned_members=["Alice"]),  # 20 of 25 -> 80%
            ItemAssignment(item_index=1, assigned_members=["Bob"]),    # 5 of 25 -> 20%
        ],
    )
    result = compute_split(request)

    alice = next(m for m in result.member_breakdowns if m.member_name == "Alice")
    bob = next(m for m in result.member_breakdowns if m.member_name == "Bob")

    assert alice.tax_share == 2.00
    assert bob.tax_share == 0.50
    assert alice.service_charge_share == 4.00
    assert bob.service_charge_share == 1.00


def test_discount_is_subtracted_proportionally():
    receipt = make_receipt()
    receipt.discount = 5.00
    receipt.printed_total = 27.50
    request = SplitRequest(
        receipt_data=receipt,
        members=["Alice", "Bob"],
        assignments=[
            ItemAssignment(item_index=0, assigned_members=["Alice"]),
            ItemAssignment(item_index=1, assigned_members=["Bob"]),
        ],
    )
    result = compute_split(request)

    alice = next(m for m in result.member_breakdowns if m.member_name == "Alice")
    bob = next(m for m in result.member_breakdowns if m.member_name == "Bob")

    assert alice.discount_share == 4.00  # 80% of 5.00
    assert bob.discount_share == 1.00    # 20% of 5.00


def test_sum_of_totals_matches_table_total():
    receipt = make_receipt()
    request = SplitRequest(
        receipt_data=receipt,
        members=["Alice", "Bob", "Carol"],
        assignments=[
            ItemAssignment(item_index=0, assigned_members=["Alice", "Bob", "Carol"]),
            ItemAssignment(item_index=1, assigned_members=["Alice"]),
        ],
    )
    result = compute_split(request)

    summed = round(sum(m.total_owed for m in result.member_breakdowns), 2)
    assert summed == result.table_total


def test_member_with_no_items_owes_zero():
    receipt = make_receipt()
    request = SplitRequest(
        receipt_data=receipt,
        members=["Alice", "Bob", "Dave"],  # Dave assigned nothing
        assignments=[
            ItemAssignment(item_index=0, assigned_members=["Alice"]),
            ItemAssignment(item_index=1, assigned_members=["Bob"]),
        ],
    )
    result = compute_split(request)
    dave = next(m for m in result.member_breakdowns if m.member_name == "Dave")
    assert dave.total_owed == 0.00


def test_invalid_item_index_raises():
    receipt = make_receipt()
    request = SplitRequest(
        receipt_data=receipt,
        members=["Alice"],
        assignments=[ItemAssignment(item_index=99, assigned_members=["Alice"])],
    )
    with pytest.raises(ValueError):
        compute_split(request)


def test_empty_assigned_members_raises():
    receipt = make_receipt()
    request = SplitRequest(
        receipt_data=receipt,
        members=["Alice"],
        assignments=[ItemAssignment(item_index=0, assigned_members=[])],
    )
    with pytest.raises(ValueError):
        compute_split(request)


def test_unknown_member_in_assignment_raises():
    receipt = make_receipt()
    request = SplitRequest(
        receipt_data=receipt,
        members=["Alice"],
        assignments=[ItemAssignment(item_index=0, assigned_members=["Zoe"])],
    )
    with pytest.raises(ValueError):
        compute_split(request)


def test_no_members_raises():
    receipt = make_receipt()
    request = SplitRequest(receipt_data=receipt, members=[], assignments=[])
    with pytest.raises(ValueError):
        compute_split(request)