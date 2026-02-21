import asyncio
import aiosqlite
import os
import sys

# Ensure Voltar is in PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import DB_PATH

async def clear_catalog():
    print(f"Connecting to database: {DB_PATH}")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('PRAGMA foreign_keys = OFF;')
        await db.execute('BEGIN IMMEDIATE')
        
        try:
            # Count records before deleting
            async with db.execute('SELECT COUNT(*) FROM favorites') as cursor:
                favs_count = (await cursor.fetchone())[0]
            
            async with db.execute('SELECT COUNT(*) FROM stock_items') as cursor:
                stock_count = (await cursor.fetchone())[0]
                
            async with db.execute('SELECT COUNT(*) FROM products') as cursor:
                prod_count = (await cursor.fetchone())[0]
                
            async with db.execute('SELECT COUNT(*) FROM categories') as cursor:
                cat_count = (await cursor.fetchone())[0]
            
            # Delete records
            await db.execute('DELETE FROM favorites')
            await db.execute('DELETE FROM stock_items')
            await db.execute('DELETE FROM products')
            await db.execute('DELETE FROM categories')
            await db.execute("DELETE FROM settings WHERE key = 'stock_update_msg'")
            
            # Reset Auto-increments
            await db.execute("DELETE FROM sqlite_sequence WHERE name IN ('categories', 'products', 'stock_items')")
            
            await db.commit()
            print("\n✅ Database cleared successfully!")
            print(f"📊 Deleted records summary:")
            print(f" - Categories deleted: {cat_count}")
            print(f" - Products deleted: {prod_count}")
            print(f" - Stock items deleted: {stock_count}")
            print(f" - Favorites deleted: {favs_count}")
        except Exception as e:
            await db.execute('ROLLBACK')
            print(f"❌ Error during cleanup: {e}")

if __name__ == "__main__":
    asyncio.run(clear_catalog())
