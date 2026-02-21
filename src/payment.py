import logging
from aiocryptopay import AioCryptoPay, Networks
from src.config import CRYPTO_BOT_TOKEN

logger = logging.getLogger(__name__)

crypto = AioCryptoPay(token=CRYPTO_BOT_TOKEN, network=Networks.MAIN_NET)

async def create_crypto_invoice(amount: float) -> dict:
    # amounts might need to be created in USDT/USD
    # For AioCryptoPay, fiat is not directly settable in some older versions, 
    # but we can set asset='USDT' assuming 1 USD = 1 USDT for simplicity
    invoice = await crypto.create_invoice(asset='USDT', amount=amount)
    return {
        'url': invoice.pay_url,
        'invoice_id': invoice.invoice_id
    }

async def check_crypto_invoice(invoice_id: int) -> bool:
    invoices = await crypto.get_invoices(invoice_ids=invoice_id)
    if invoices:
        return invoices[0].status == 'paid'
    return False

async def close_payment_session():
    await crypto.session.close()
