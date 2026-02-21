import logging
from aiocryptopay import AioCryptoPay, Networks
from src.config import CRYPTO_BOT_TOKEN

logger = logging.getLogger(__name__)

_crypto_client = None

def get_crypto_client():
    global _crypto_client
    if _crypto_client is None:
        _crypto_client = AioCryptoPay(token=CRYPTO_BOT_TOKEN, network=Networks.MAIN_NET)
    return _crypto_client

async def create_crypto_invoice(amount: float) -> dict:
    crypto = get_crypto_client()
    invoice = await crypto.create_invoice(asset='USDT', amount=amount)
    return {
        'url': invoice.bot_invoice_url,
        'invoice_id': invoice.invoice_id
    }

async def get_crypto_invoice_status(invoice_id: int) -> str:
    crypto = get_crypto_client()
    try:
        invoice = await crypto.get_invoices(invoice_ids=invoice_id)
        if invoice:
            if isinstance(invoice, list):
                return invoice[0].status
            return invoice.status
    except Exception as e:
        logger.error(f"Error checking crypto bot invoice {invoice_id}: {e}")
    return "error"

async def close_payment_session():
    if _crypto_client:
        await _crypto_client.close()
