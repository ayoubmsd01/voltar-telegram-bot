"""xRocket Pay API (Current version). REST polling only, no incoming webhook."""
import os
import logging
from decimal import Decimal
import aiohttp

logger = logging.getLogger(__name__)
BASE_URL = "https://pay.api.xrocket.exchange"


def _token():
    token = os.getenv("XROCKET_API_TOKEN", "").strip()
    if not token:
        raise RuntimeError("xRocket Pay is not configured")
    return token


async def _request(method, path, *, json_body=None, params=None):
    headers = {"Authorization": "Bearer " + _token(), "Accept": "application/json"}
    if json_body is not None:
        headers["Content-Type"] = "application/json"
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.request(method, BASE_URL + path, headers=headers,
                                   json=json_body, params=params) as response:
            if response.status not in (200, 201):
                logger.warning("xRocket API returned HTTP %s on %s", response.status, path)
                raise RuntimeError("xRocket payment provider request failed")
            data = await response.json()
            if not isinstance(data, dict):
                raise ValueError("Invalid xRocket invoice response")
            return data


async def create_xrocket_invoice(amount, local_id, telegram_user_id):
    value = Decimal(str(amount)).quantize(Decimal("0.01"))
    if value <= 0:
        raise ValueError("Amount must be positive")
    result = await _request("POST", "/api/v1/invoices", json_body={
        "priceAmount": format(value, ".2f"),
        "priceCurrency": "USDT",
        "payoutCurrency": "USDT",
        "numPayments": 1,
        "clientInvoiceId": local_id,
        "customer": {"telegramId": str(telegram_user_id)},
        "description": "VOLTAR SHOP balance top-up",
        "expiresIn": 3600000
    })
    link = (result.get("links") or {}).get("telegramBotLink")
    invoice_id = result.get("id")
    if not link or not invoice_id or str(result.get("priceCurrency")) != "USDT":
        raise ValueError("xRocket returned an incomplete invoice")
    if Decimal(str(result.get("priceAmount"))) != value:
        raise ValueError("xRocket invoice amount mismatch")
    return {"url": link, "invoice_id": str(invoice_id)}


async def get_xrocket_invoice_status(invoice_id, expected_amount):
    result = await _request("GET", "/api/v1/invoice",
                            params={"invoiceId": str(invoice_id)})
    if str(result.get("id")) != str(invoice_id):
        raise ValueError("xRocket invoice ID mismatch")
    if str(result.get("priceCurrency")) != "USDT":
        raise ValueError("xRocket invoice currency mismatch")
    if Decimal(str(result.get("priceAmount"))) != Decimal(str(expected_amount)):
        raise ValueError("xRocket invoice amount mismatch")
    return str(result.get("status", "unknown"))
