from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.models import LineItem, ReceiptData

client = TestClient(app)


def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_upload_receipt_rejects_bad_content_type():
    res = client.post(
        "/api/upload-receipt",
        files=[("files", ("receipt.txt", b"not an image", "text/plain"))],
    )
    assert res.status_code == 415


def test_upload_receipt_requires_files():
    res = client.post("/api/upload-receipt", files=[])
    assert res.status_code in (400, 422)  # 422 if FastAPI rejects empty multipart entirely


@patch("app.main.extract_receipt_data_multi", new_callable=AsyncMock)
def test_upload_receipt_success_single_file(mock_extract):
    mock_extract.return_value = ReceiptData(
        items=[LineItem(name="Coffee", quantity=1, price=4.50, confidence=0.97)],
        subtotal=4.50,
        tax=0.40,
        service_charge=0.0,
        discount=0.0,
        printed_total=4.90,
        math_is_valid=True,
        math_notes=None,
    )
    fake_image = b"\xff\xd8\xff\xe0fakejpegcontent"
    res = client.post(
        "/api/upload-receipt",
        files=[("files", ("receipt.jpg", fake_image, "image/jpeg"))],
    )
    assert res.status_code == 200
    body = res.json()
    assert body["items"][0]["name"] == "Coffee"
    assert body["math_is_valid"] is True


@patch("app.main.extract_receipt_data_multi", new_callable=AsyncMock)
def test_upload_receipt_success_multi_page(mock_extract):
    mock_extract.return_value = ReceiptData(
        items=[LineItem(name="Burger", quantity=1, price=12.00, confidence=0.9)],
        subtotal=12.00,
        tax=1.00,
        service_charge=0.0,
        discount=0.0,
        printed_total=13.00,
        math_is_valid=True,
        math_notes=None,
    )
    page1 = b"\xff\xd8\xff\xe0page1"
    page2 = b"\xff\xd8\xff\xe0page2"
    res = client.post(
        "/api/upload-receipt",
        files=[
            ("files", ("receipt_p1.jpg", page1, "image/jpeg")),
            ("files", ("receipt_p2.jpg", page2, "image/jpeg")),
        ],
    )
    assert res.status_code == 200
    # extract_receipt_data_multi should have been called once with both images
    mock_extract.assert_called_once()
    called_images = mock_extract.call_args[0][0]
    assert len(called_images) == 2


def test_calculate_split_success():
    payload = {
        "receipt_data": {
            "items": [{"name": "Pizza", "quantity": 1, "price": 20.00, "confidence": 0.98}],
            "subtotal": 20.00,
            "tax": 2.00,
            "service_charge": 0.0,
            "discount": 0.0,
            "printed_total": 22.00,
            "math_is_valid": True,
            "math_notes": None,
        },
        "members": ["Alice"],
        "assignments": [{"item_index": 0, "assigned_members": ["Alice"]}],
    }
    res = client.post("/api/calculate-split", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert body["member_breakdowns"][0]["total_owed"] == 22.00


def test_calculate_split_bad_item_index():
    payload = {
        "receipt_data": {
            "items": [{"name": "Pizza", "quantity": 1, "price": 20.00, "confidence": 0.98}],
            "subtotal": 20.00,
            "tax": 0.0,
            "service_charge": 0.0,
            "discount": 0.0,
            "printed_total": 20.00,
            "math_is_valid": True,
            "math_notes": None,
        },
        "members": ["Alice"],
        "assignments": [{"item_index": 5, "assigned_members": ["Alice"]}],
    }
    res = client.post("/api/calculate-split", json=payload)
    assert res.status_code == 400


def test_calculate_split_unknown_member():
    payload = {
        "receipt_data": {
            "items": [{"name": "Pizza", "quantity": 1, "price": 20.00, "confidence": 0.98}],
            "subtotal": 20.00,
            "tax": 0.0,
            "service_charge": 0.0,
            "discount": 0.0,
            "printed_total": 20.00,
            "math_is_valid": True,
            "math_notes": None,
        },
        "members": ["Alice"],
        "assignments": [{"item_index": 0, "assigned_members": ["Zoe"]}],
    }
    res = client.post("/api/calculate-split", json=payload)
    assert res.status_code == 400