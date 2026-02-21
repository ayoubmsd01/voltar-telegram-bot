import logging
import aiosqlite
from typing import Optional, List, Dict, Any

from .config import DB_PATH

logger = logging.getLogger(__name__)

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT,
                language TEXT DEFAULT 'en',
                balance REAL DEFAULT 0,
                total_spent REAL DEFAULT 0,
                registered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                is_banned BOOLEAN DEFAULT 0
            )
        ''')
        # Try altering if exists
        try:
            await db.execute('ALTER TABLE users ADD COLUMN username TEXT')
        except:
            pass

        await db.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name_ru TEXT,
                name_en TEXT
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id INTEGER,
                title_ru TEXT,
                title_en TEXT,
                desc_ru TEXT,
                desc_en TEXT,
                price REAL,
                FOREIGN KEY(category_id) REFERENCES categories(id) ON DELETE CASCADE
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS stock_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER,
                type TEXT, 
                content TEXT,
                status TEXT DEFAULT 'available',
                reserved_at DATETIME,
                FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
            )
        ''')
        
        # type can be: file, link, code
        # status can be: available, reserved, sold

        await db.execute('''
            CREATE TABLE IF NOT EXISTS purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                product_id INTEGER,
                stock_item_id INTEGER,
                price_paid REAL,
                used_balance REAL DEFAULT 0,
                paid_crypto REAL DEFAULT 0,
                invoice_id TEXT,
                purchased_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(product_id) REFERENCES products(id),
                FOREIGN KEY(stock_item_id) REFERENCES stock_items(id)
            )
        ''')
        
        try:
            await db.execute('ALTER TABLE purchases ADD COLUMN used_balance REAL DEFAULT 0')
            await db.execute('ALTER TABLE purchases ADD COLUMN paid_crypto REAL DEFAULT 0')
            await db.execute('ALTER TABLE purchases ADD COLUMN invoice_id TEXT')
        except Exception:
            pass

        await db.execute('''
            CREATE TABLE IF NOT EXISTS favorites (
                user_id INTEGER,
                product_id INTEGER,
                PRIMARY KEY (user_id, product_id),
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS invoices (
                invoice_id TEXT PRIMARY KEY,
                user_id INTEGER,
                amount REAL,
                status TEXT DEFAULT 'active',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')

        await db.commit()

async def get_db() -> aiosqlite.Connection:
    return await aiosqlite.connect(DB_PATH)

def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

async def get_user(user_id: int) -> Optional[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = dict_factory
        async with db.execute('SELECT * FROM users WHERE id = ?', (user_id,)) as cursor:
            return await cursor.fetchone()

async def create_user(user_id: int, language: str = 'en', username: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('INSERT OR IGNORE INTO users (id, language, username) VALUES (?, ?, ?)', (user_id, language, username))
        await db.execute('UPDATE users SET username = ? WHERE id = ?', (username, user_id))
        await db.commit()

async def update_user_language(user_id: int, language: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET language = ? WHERE id = ?', (language, user_id))
        await db.commit()

async def update_user_balance(user_id: int, diff: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET balance = balance + ? WHERE id = ?', (diff, user_id))
        await db.commit()

async def set_user_ban(user_id: int, is_banned: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET is_banned = ? WHERE id = ?', (1 if is_banned else 0, user_id))
        await db.commit()

async def check_user_banned(user_id: int) -> bool:
    user = await get_user(user_id)
    if user:
        return bool(user['is_banned'])
    return False

# Settings
async def get_setting(key: str) -> Optional[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT value FROM settings WHERE key = ?', (key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def set_setting(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
        await db.commit()

async def delete_setting(key: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('DELETE FROM settings WHERE key = ?', (key,))
        await db.commit()

# Categories
async def get_categories() -> List[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = dict_factory
        async with db.execute('SELECT * FROM categories') as cursor:
            return await cursor.fetchall()
            
async def add_category(name_ru: str, name_en: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('INSERT INTO categories (name_ru, name_en) VALUES (?, ?)', (name_ru, name_en))
        await db.commit()
        return cursor.lastrowid

# Products
async def get_products_by_category(category_id: int) -> List[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = dict_factory
        # Include stock count directly in the query
        query = '''
            SELECT p.*, 
                   (SELECT COUNT(*) FROM stock_items s WHERE s.product_id = p.id AND s.status = 'available') as stock_count
            FROM products p
            WHERE p.category_id = ?
        '''
        async with db.execute(query, (category_id,)) as cursor:
            return await cursor.fetchall()

async def get_all_products() -> List[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = dict_factory
        query = '''
            SELECT p.*, 
                   (SELECT COUNT(*) FROM stock_items s WHERE s.product_id = p.id AND s.status = 'available') as stock_count
            FROM products p
        '''
        async with db.execute(query) as cursor:
            return await cursor.fetchall()

async def get_product(product_id: int) -> Optional[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = dict_factory
        query = '''
            SELECT p.*, 
                   (SELECT COUNT(*) FROM stock_items s WHERE s.product_id = p.id AND s.status = 'available') as stock_count
            FROM products p
            WHERE p.id = ?
        '''
        async with db.execute(query, (product_id,)) as cursor:
            return await cursor.fetchone()

async def add_product(category_id: int, title_ru: str, title_en: str, desc_ru: str, desc_en: str, price: float) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('''
            INSERT INTO products (category_id, title_ru, title_en, desc_ru, desc_en, price) 
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (category_id, title_ru, title_en, desc_ru, desc_en, price))
        await db.commit()
        return cursor.lastrowid

# Stock
async def add_stock_item(product_id: int, item_type: str, content: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('''
            INSERT INTO stock_items (product_id, type, content, status) 
            VALUES (?, ?, ?, 'available')
        ''', (product_id, item_type, content))
        await db.commit()
        return cursor.lastrowid

async def reserve_stock_item(product_id: int) -> Optional[int]:
    """Reserves one available stock item and returns its ID, or None if out of stock."""
    # Transactions need to be carefully done. SQLite with aiosqlite isolates by default per connection,
    # but we need to ensure we lock. Use BEGIN EXCLUSIVE
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = dict_factory
        await db.execute('BEGIN EXCLUSIVE')
        
        # Check available stock
        async with db.execute('SELECT id FROM stock_items WHERE product_id = ? AND status = ? LIMIT 1', 
                              (product_id, 'available')) as cursor:
            row = await cursor.fetchone()
            
        if not row:
            await db.execute('ROLLBACK')
            return None
            
        item_id = row['id']
        # Set to reserved
        await db.execute('UPDATE stock_items SET status = ?, reserved_at = CURRENT_TIMESTAMP WHERE id = ?', 
                         ('reserved', item_id))
        await db.commit()
        return item_id

async def release_stock_item(stock_item_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE stock_items SET status = ?, reserved_at = NULL WHERE id = ?', 
                         ('available', stock_item_id))
        await db.commit()

async def mark_stock_sold(stock_item_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE stock_items SET status = ? WHERE id = ?', ('sold', stock_item_id))
        await db.commit()

async def get_stock_item(stock_item_id: int) -> Optional[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = dict_factory
        async with db.execute('SELECT * FROM stock_items WHERE id = ?', (stock_item_id,)) as cursor:
            return await cursor.fetchone()

# Favorites
async def add_favorite(user_id: int, product_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('INSERT OR IGNORE INTO favorites (user_id, product_id) VALUES (?, ?)', (user_id, product_id))
        await db.commit()

async def get_favorites(product_id: int) -> List[int]:
    """Get list of user IDs who favorited this product"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT user_id FROM favorites WHERE product_id = ?', (product_id,)) as cursor:
            rows = await cursor.fetchall()
            return [r[0] for r in rows]

async def remove_favorites_for_product(product_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('DELETE FROM favorites WHERE product_id = ?', (product_id,))
        await db.commit()

# Invoices
async def create_invoice(invoice_id: str, user_id: int, amount: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('INSERT INTO invoices (invoice_id, user_id, amount) VALUES (?, ?, ?)', 
                         (invoice_id, user_id, amount))
        await db.commit()

async def get_invoice(invoice_id: str) -> Optional[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = dict_factory
        async with db.execute('SELECT * FROM invoices WHERE invoice_id = ?', (invoice_id,)) as cursor:
            return await cursor.fetchone()

async def update_invoice_status(invoice_id: str, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE invoices SET status = ? WHERE invoice_id = ?', (status, invoice_id))
        await db.commit()

async def process_invoice_payment(invoice_id: str, user_id: int, amount: float) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('BEGIN IMMEDIATE')
        try:
            db.row_factory = dict_factory
            async with db.execute('SELECT status FROM invoices WHERE invoice_id = ?', (invoice_id,)) as cursor:
                row = await cursor.fetchone()
            
            if not row or row['status'] == 'paid':
                await db.execute('ROLLBACK')
                return False
                
            await db.execute("UPDATE invoices SET status = 'paid' WHERE invoice_id = ?", (invoice_id,))
            await db.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, user_id))
            await db.commit()
            return True
        except Exception as e:
            await db.execute('ROLLBACK')
            import logging
            logging.getLogger(__name__).error(f"Error in process_invoice_payment: {e}")
            raise

# Purchases
async def add_purchase(user_id: int, product_id: int, stock_item_id: int, price_paid: float):
    async with aiosqlite.connect(DB_PATH) as db:
        # Also increment total spent
        await db.execute('BEGIN TRANSACTION')
        await db.execute('INSERT INTO purchases (user_id, product_id, stock_item_id, price_paid) VALUES (?, ?, ?, ?)', 
                         (user_id, product_id, stock_item_id, price_paid))
        await db.execute('UPDATE users SET total_spent = total_spent + ? WHERE id = ?', (price_paid, user_id))
        await db.commit()

async def get_user_purchases(user_id: int) -> List[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = dict_factory
        query = '''
            SELECT p.*, pr.title_ru, pr.title_en 
            FROM purchases p
            JOIN products pr ON p.product_id = pr.id
            WHERE p.user_id = ?
            ORDER BY p.purchased_at DESC
        '''
        async with db.execute(query, (user_id,)) as cursor:
            return await cursor.fetchall()
        
async def get_user_topups(user_id: int) -> List[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = dict_factory
        query = '''
            SELECT * FROM invoices 
            WHERE user_id = ? AND status = 'paid'
            ORDER BY created_at DESC
        '''
        async with db.execute(query, (user_id,)) as cursor:
            return await cursor.fetchall()

async def get_all_users() -> List[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = dict_factory
        async with db.execute('SELECT * FROM users ORDER BY registered_at ASC') as cursor:
            return await cursor.fetchall()

async def get_active_users() -> List[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = dict_factory
        async with db.execute('SELECT id, language FROM users WHERE is_banned = 0 ORDER BY registered_at ASC') as cursor:
            return await cursor.fetchall()
async def get_purchases_page(offset: int = 0, limit: int = 10, user_id=None, order_id=None) -> Dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = dict_factory
        
        where_clause = ""
        params = []
        if user_id:
            where_clause = "WHERE pu.user_id = ?"
            params.append(user_id)
        elif order_id:
            where_clause = "WHERE pu.id = ?"
            params.append(order_id)
            
        count_query = f"SELECT COUNT(*) as c FROM purchases pu {where_clause}"
        async with db.execute(count_query, params) as cursor:
            count = (await cursor.fetchone())['c']
            
        params.extend([limit, offset])
        query = f"""
            SELECT pu.id as order_id, pu.user_id, pu.price_paid, pu.used_balance, pu.paid_crypto, pu.invoice_id, pu.purchased_at,
                   u.username, pr.title_en, pr.title_ru, si.type as deliver_type, si.content as deliver_content
            FROM purchases pu
            LEFT JOIN users u ON pu.user_id = u.id
            LEFT JOIN products pr ON pu.product_id = pr.id
            LEFT JOIN stock_items si ON pu.stock_item_id = si.id
            {where_clause}
            ORDER BY pu.purchased_at DESC
            LIMIT ? OFFSET ?
        """
        async with db.execute(query, params) as cursor:
            data = await cursor.fetchall()
            
        return {'total': count, 'data': data}
