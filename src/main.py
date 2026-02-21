import logging
import sys
from telegram.ext import Application
from src.config import BOT_TOKEN
from src.db import init_db
from src.payment import close_payment_session

# Import handlers
from src.handlers import user, admin, catalog, profile

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

import traceback
import json

async def error_handler(update, context):
    logger.error("Exception while handling an update:", exc_info=context.error)
    # Get traceback into string
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)
    logger.error(f"Full Traceback:\n{tb_string}")

async def post_init(application: Application):
    await init_db()
    logger.info("Database initialized")

async def post_stop(application: Application):
    await close_payment_session()
    logger.info("Payment session closed")

def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not set. Assuming this is the placeholder web service. Starting dummy server...")
        import os
        import time
        import http.server
        import socketserver
        
        PORT = int(os.environ.get("PORT", 8080))
        class HealthCheckHandler(http.server.SimpleHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-type", "text/plain")
                self.end_headers()
                self.wfile.write(b"OK")
            def log_message(self, format, *args):
                pass
        
        try:
            with socketserver.TCPServer(("", PORT), HealthCheckHandler) as httpd:
                logger.info(f"Dummy healthcheck server starting at port {PORT}")
                httpd.serve_forever()
        except Exception as e:
            logger.error(f"Dummy server failed to start: {e}. Sleeping forever instead.")
            while True:
                time.sleep(3600)
        return

    application = Application.builder().token(BOT_TOKEN).post_init(post_init).post_stop(post_stop).build()

    # Add handlers
    user.register_handlers(application)
    admin.register_handlers(application)
    catalog.register_handlers(application)
    profile.register_handlers(application)

    application.add_error_handler(error_handler)

    logger.info("Starting polling...")
    application.run_polling()

if __name__ == "__main__":
    main()
