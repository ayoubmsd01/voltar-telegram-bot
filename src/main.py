import logging
import sys
import os
import aiosqlite
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
    
    if os.environ.get("CLEAR_CATALOG_ON_START") == "1":
        from src.config import DB_PATH
        abs_db_path = os.path.abspath(DB_PATH)
        logger.info(f"--- CATALOG CLEANUP TRIGGERED ---")
        logger.info(f"Env CLEAR_CATALOG_ON_START = 1")
        logger.info(f"DB_PATH resolved to: {abs_db_path}")
        
        async with aiosqlite.connect(DB_PATH) as db:
            # Check existing tables
            async with db.execute("SELECT name FROM sqlite_master WHERE type='table';") as cursor:
                tables = await cursor.fetchall()
                table_names = [t[0] for t in tables]
                logger.info(f"Existing tables in DB: {table_names}")

            # Backup check if required tables exist
            if 'categories' not in table_names:
                logger.warning("Tables like 'categories' not found, maybe using the wrong database file!")

            logger.info("Starting safe deletion process...")
            
            try:
                # Disable FKs for the duration of the connection's transaction logic
                await db.execute('PRAGMA foreign_keys = OFF;')
                await db.execute('BEGIN IMMEDIATE;')
                
                # Count
                async with db.execute('SELECT COUNT(*) FROM favorites') as cursor: favs_count = (await cursor.fetchone())[0]
                async with db.execute('SELECT COUNT(*) FROM stock_items') as cursor: stock_count = (await cursor.fetchone())[0]
                async with db.execute('SELECT COUNT(*) FROM products') as cursor: prod_count = (await cursor.fetchone())[0]
                async with db.execute('SELECT COUNT(*) FROM categories') as cursor: cat_count = (await cursor.fetchone())[0]
                
                # Delete
                await db.execute('DELETE FROM favorites')
                await db.execute('DELETE FROM stock_items')
                await db.execute('DELETE FROM products')
                await db.execute('DELETE FROM categories')
                await db.execute("DELETE FROM settings WHERE key = 'stock_update_msg'")
                
                # Reset sequences
                await db.execute("DELETE FROM sqlite_sequence WHERE name IN ('categories', 'products', 'stock_items')")
                
                await db.commit()
                # Re-enable FKs after successful commit
                await db.execute('PRAGMA foreign_keys = ON;')
                
                # Vacuum outside of transaction
                await db.execute('VACUUM;')
                
                logger.info("✅ Catalog cleared successfully!")
                logger.info(f"📊 Deleted records report:")
                logger.info(f" - categories deleted: {cat_count}")
                logger.info(f" - products deleted: {prod_count}")
                logger.info(f" - stock_items deleted: {stock_count}")
                logger.info(f" - favorites deleted: {favs_count}")
                
                # Verification
                async with db.execute('SELECT COUNT(*) FROM favorites') as cursor: v_favs = (await cursor.fetchone())[0]
                async with db.execute('SELECT COUNT(*) FROM stock_items') as cursor: v_stock = (await cursor.fetchone())[0]
                async with db.execute('SELECT COUNT(*) FROM products') as cursor: v_prod = (await cursor.fetchone())[0]
                async with db.execute('SELECT COUNT(*) FROM categories') as cursor: v_cat = (await cursor.fetchone())[0]
                
                logger.info("📊 Verification counts (should be all 0):")
                logger.info(f"categories = {v_cat}, products = {v_prod}, stock_items = {v_stock}, favorites = {v_favs}")
                
                if sum([v_cat, v_prod, v_stock, v_favs]) == 0:
                    logger.info("✅ Verification MATCH: All catalog items removed.")
                else:
                    logger.error("❌ Verification FAILED: Some items remained in DB.")
                    
                logger.warning("⚠️ PLEASE REMOVE 'CLEAR_CATALOG_ON_START' FROM ENVIRONMENT VARIABLES TO PREVENT WIPING ON NEXT RESTART.")
            except Exception as e:
                await db.execute('ROLLBACK')
                logger.error(f"❌ Error during catalog cleanup:")
                logger.error(traceback.format_exc())

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
