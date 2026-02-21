import asyncio
from src.payment import create_crypto_invoice, get_crypto_client

async def main():
    try:
        data = await create_crypto_invoice(1.5)
        print("Success:", data)
    except Exception as e:
        print("Error:", repr(e))
    client = get_crypto_client()
    if client:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())
