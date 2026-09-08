"""
Vision service using Groq API to extract receipt data into our category-aware
ReceiptData schema (per-item categories, distinct scoped tax/service/discount
charge lines — never lumped into one pool).
"""
from __future__ import annotations

import base64
import io
import json
import os
from decimal import Decimal

from dotenv import load_dotenv
from groq import Groq
from PIL import Image

from app.models import ReceiptData

load_dotenv()

MODEL_NAME = "qwen/qwen3.6-27b"
MAX_DIMENSION = 2048
MAX_IMAGES = 3
MATH_TOLERANCE = Decimal("0.05")

_EXAMPLE_JSON = """{
  "items": [
    {"name": "Iced Tea", "category": "Beverage", "quantity": 1, "price": 3.29, "confidence": 0.95},
    {"name": "Garlic Bread", "category": "Food", "quantity": 1, "price": 9.99, "confidence": 0.9}
  ],
  "charges": [
    {"label": "Food Taxable VAT", "charge_type": "tax", "category": "Food", "amount": 5.00},
    {"label": "Beverage Taxable VAT", "charge_type": "tax", "category": "Beverage", "amount": 1.00},
    {"label": "Service Charge", "charge_type": "service_charge", "category": null, "amount": 10.00},
    {"label": "Loyalty Discount", "charge_type": "discount", "category": null, "amount": 2.00}
  ],
  "subtotal": 13.28,
  "printed_total": 27.28,
  "currency": "INR",
  "math_is_valid": true,
  "math_notes": null
}"""

SYSTEM_INSTRUCTION = (
    "You are an expert financial OCR extraction and proportional bill-splitting "
    "engine. Process the receipt image and extract EVERY line item printed on "
    "it — do not skip or merge any.\n\n"
    "For each item, assign a 'category' (e.g. Food, Beverage, Service, "
    "Alcohol, Dessert) so category-specific charges can be mapped correctly "
    "without cross-subsidization.\n\n"
    "Explicitly separate every distinct fee, tax, and service charge printed "
    "on the receipt. NEVER lump different taxes or charges into a single "
    "number — if the receipt shows a 'Food Tax' and a separate 'Beverage "
    "Tax', output two separate charge entries, each with its own 'category'. "
    "If a charge applies to the whole bill (like a flat service charge or "
    "an overall discount), set its 'category' to null. If the receipt only "
    "has one flat tax line (not split by category), still include it as a "
    "single charge entry with 'category' set to null — never omit a charge "
    "line that is printed on the receipt.\n\n"
    "CURRENCY RULE: If the receipt contains a '$' symbol anywhere on it, set "
    "'currency' to 'USD'. If it does NOT contain a '$' symbol, default to "
    "'INR' (assume Indian Rupees) unless another currency symbol/code is "
    "unmistakably printed (e.g. '€' -> EUR, '£' -> GBP) — in that specific "
    "case use that currency's ISO code instead.\n\n"
    "Respond with ONLY a single valid JSON object, no markdown fences, no "
    "commentary, matching exactly this structure and field names:\n\n"
    f"{_EXAMPLE_JSON}\n\n"
    "Rules:\n"
    "- charge_type must be exactly one of: 'tax', 'service_charge', 'discount'.\n"
    "- 'amount' on every charge is always a positive number; the type conveys the sign.\n"
    "- If the receipt has no separate categories, use 'Uncategorized' for all items "
    "and set every charge's category to null (whole-bill charges).\n"
    "- Do not invent fields that are not in the example above."
)


class VisionServiceError(RuntimeError):
    pass


def _get_client() -> Groq:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise VisionServiceError("GROQ_API_KEY is missing from your .env file.")
    return Groq(api_key=api_key)


def _prepare_image(image_bytes: bytes) -> bytes:
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            img = img.convert("RGB")
            width, height = img.size
            longest_edge = max(width, height)
            if longest_edge > MAX_DIMENSION:
                scale = MAX_DIMENSION / longest_edge
                new_size = (int(width * scale), int(height * scale))
                img = img.resize(new_size, Image.LANCZOS)
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=90)
            return buffer.getvalue()
    except Exception as exc:
        raise VisionServiceError(f"Could not read image: {exc}") from exc


def _apply_math_check(receipt: ReceiptData) -> ReceiptData:
    computed_items_sum = sum((Decimal(str(item.price)) for item in receipt.items), Decimal("0"))
    stated_subtotal = Decimal(str(receipt.subtotal))
    deviation = abs(computed_items_sum - stated_subtotal)

    if deviation > MATH_TOLERANCE:
        receipt.math_is_valid = False
        receipt.math_notes = (
            f"Sum of line items ({computed_items_sum}) deviates from stated "
            f"subtotal ({stated_subtotal}) by {deviation}."
        )
    else:
        receipt.math_is_valid = True
        receipt.math_notes = None

    return receipt


def _call_groq(image_bytes_list: list[bytes]) -> ReceiptData:
    if len(image_bytes_list) > MAX_IMAGES:
        raise VisionServiceError(
            f"Too many images ({len(image_bytes_list)}); this model supports at most {MAX_IMAGES}."
        )

    client = _get_client()

    content_messages = [{"type": "text", "text": SYSTEM_INSTRUCTION}]
    for img_bytes in image_bytes_list:
        base64_image = base64.b64encode(img_bytes).decode("utf-8")
        content_messages.append(
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
        )
    content_messages.append(
        {"type": "text", "text": "Extract the full receipt data now, as JSON only."}
    )

    try:
        chat_completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": content_messages}],
            response_format={"type": "json_object"},
            temperature=0.0,
            max_completion_tokens=950,  # stay under Groq free-tier 1000 OTPM/min cap
            reasoning_effort="none",
        )
        response_text = chat_completion.choices[0].message.content
        if not response_text or not response_text.strip():
            raise VisionServiceError("Model returned an empty response.")

        data = json.loads(response_text)

        data.setdefault("items", [])
        data.setdefault("charges", [])
        data.setdefault("subtotal", 0.0)
        data.setdefault("printed_total", data.get("subtotal", 0.0))
        data.setdefault("currency", "INR")
        data.setdefault("math_is_valid", True)
        data.setdefault("math_notes", None)

        for item in data["items"]:
            item.setdefault("category", "Uncategorized")

        if not data["items"]:
            raise VisionServiceError(
                "Model did not extract any line items from the image. "
                "Try a clearer or better-lit photo of the receipt."
            )

        # --- Safety net: if the model extracted items but reported no
        # tax/service/discount charge lines at all, and the printed total is
        # meaningfully higher than the sum of item prices, synthesize a
        # single generic charge line for the difference. This guarantees the
        # user always sees SOMETHING to review/edit on Screen 2 (and that
        # splitter.py has something to distribute), instead of silently
        # losing all tax/service-charge distribution when the model omits it.
        computed_items_sum = sum(float(item.get("price", 0)) for item in data["items"])
        try:
            printed_total = float(data["printed_total"]) if data["printed_total"] else 0.0
        except (TypeError, ValueError):
            printed_total = 0.0

        if not data["charges"] and printed_total > 0:
            diff = round(printed_total - computed_items_sum, 2)
            if diff > 0.01:
                data["charges"].append(
                    {
                        "label": "Tax & Charges (auto-detected — please verify)",
                        "charge_type": "tax",
                        "category": None,
                        "amount": diff,
                    }
                )

        receipt = ReceiptData.model_validate(data)
        return _apply_math_check(receipt)

    except VisionServiceError:
        raise
    except Exception as exc:
        raise VisionServiceError(f"Groq extraction failed: {exc}") from exc


async def extract_receipt_data(image_bytes: bytes) -> ReceiptData:
    normalized = _prepare_image(image_bytes)
    return _call_groq([normalized])


async def extract_receipt_data_multi(images: list[bytes]) -> ReceiptData:
    if not images:
        raise VisionServiceError("No images provided")
    normalized = [_prepare_image(img) for img in images]
    return _call_groq(normalized)