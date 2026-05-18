import aiosqlite


class DatabaseHandler:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def initialize(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    balance INTEGER DEFAULT 0,
                    referred_by INTEGER
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS configs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    config_content TEXT NOT NULL,
                    category TEXT NOT NULL,
                    is_sold INTEGER DEFAULT 0
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    price INTEGER DEFAULT 0
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    amount INTEGER NOT NULL,
                    type TEXT NOT NULL CHECK(type IN ('recharge', 'purchase')),
                    description TEXT,
                    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_transactions_user_time
                ON transactions(user_id, timestamp)
                """
            )

            # Backward-compatible migration for old databases.
            try:
                await db.execute("ALTER TABLE configs ADD COLUMN sold_to INTEGER")
            except aiosqlite.OperationalError:
                pass

            try:
                await db.execute("ALTER TABLE configs ADD COLUMN sold_at TEXT")
            except aiosqlite.OperationalError:
                pass
            try:
                await db.execute("ALTER TABLE configs ADD COLUMN model TEXT")
            except aiosqlite.OperationalError:
                pass
            try:
                await db.execute("ALTER TABLE configs ADD COLUMN title TEXT")
            except aiosqlite.OperationalError:
                pass
            try:
                await db.execute("ALTER TABLE configs ADD COLUMN price INTEGER DEFAULT 0")
            except aiosqlite.OperationalError:
                pass
            try:
                await db.execute("ALTER TABLE configs ADD COLUMN duration TEXT DEFAULT 'نامشخص'")
            except aiosqlite.OperationalError:
                pass
            try:
                await db.execute("ALTER TABLE configs ADD COLUMN description TEXT DEFAULT ''")
            except aiosqlite.OperationalError:
                pass
            try:
                await db.execute("ALTER TABLE configs ADD COLUMN stock INTEGER DEFAULT 1")
            except aiosqlite.OperationalError:
                pass
            try:
                await db.execute("ALTER TABLE configs ADD COLUMN is_active INTEGER DEFAULT 1")
            except aiosqlite.OperationalError:
                pass
            try:
                await db.execute("ALTER TABLE configs ADD COLUMN created_at TEXT")
            except aiosqlite.OperationalError:
                pass
            try:
                await db.execute("ALTER TABLE users ADD COLUMN referred_by INTEGER")
            except aiosqlite.OperationalError:
                pass

            await db.execute(
                """
                UPDATE configs
                SET
                    title = COALESCE(NULLIF(TRIM(title), ''), category, 'Config #' || id),
                    price = COALESCE(price, 0),
                    duration = COALESCE(NULLIF(TRIM(duration), ''), 'نامشخص'),
                    description = COALESCE(description, ''),
                    stock = CASE
                        WHEN stock IS NULL AND is_sold = 0 THEN 1
                        WHEN stock IS NULL THEN 0
                        ELSE stock
                    END,
                    is_active = COALESCE(is_active, 1),
                    created_at = COALESCE(created_at, datetime('now'))
                """
            )
            await db.execute(
                """
                UPDATE configs
                SET model = CASE
                    WHEN model IS NULL OR TRIM(model) = '' THEN
                        CASE
                            WHEN lower(COALESCE(category, '')) LIKE '%multi%' THEN 'nox_multi'
                            ELSE 'nox_plus'
                        END
                    ELSE model
                END
                """
            )
            await db.execute(
                """
                UPDATE configs
                SET price = COALESCE(
                    (SELECT c.price FROM categories c WHERE c.name = configs.category LIMIT 1),
                    price,
                    0
                )
                WHERE (price IS NULL OR price = 0)
                """
            )

            await db.execute(
                """
                INSERT OR IGNORE INTO categories (name)
                SELECT DISTINCT category
                FROM configs
                WHERE category IS NOT NULL AND TRIM(category) != ''
                """
            )
            await db.commit()

    async def get_setting(self, key: str, default: str | None = None) -> str | None:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT value FROM settings WHERE key = ?",
                (key,),
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else default

    async def set_setting(self, key: str, value: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )
            await db.commit()

    async def add_user_if_not_exists(self, user_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO users (user_id) VALUES (?)",
                (user_id,),
            )
            await db.commit()

    async def add_user_with_referrer(self, user_id: int, referred_by: int | None = None) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO users (user_id, referred_by) VALUES (?, ?)",
                (user_id, referred_by),
            )
            await db.commit()

    async def user_exists(self, user_id: int) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,)) as cursor:
                return await cursor.fetchone() is not None

    async def add_user(self, user_id: int) -> None:
        await self.add_user_if_not_exists(user_id)

    async def get_user_balance(self, user_id: int) -> int:
        await self.add_user_if_not_exists(user_id)
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT balance FROM users WHERE user_id = ?",
                (user_id,),
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    async def update_balance(self, user_id: int, amount: int) -> None:
        await self.add_user_if_not_exists(user_id)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET balance = balance + ? WHERE user_id = ?",
                (amount, user_id),
            )
            await db.commit()

    async def add_balance(self, user_id: int, amount: int) -> None:
        await self.update_balance(user_id, amount)

    async def add_config(self, content: str, category: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO categories (name) VALUES (?)",
                (category,),
            )
            await db.execute(
                """
                INSERT INTO configs (config_content, category)
                VALUES (?, ?)
                """,
                (content, category),
            )
            await db.commit()

    async def get_stock_count(self) -> list[tuple[str, int]]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT category, COUNT(*)
                FROM configs
                WHERE is_sold = 0
                GROUP BY category
                ORDER BY category
                """
            ) as cursor:
                return await cursor.fetchall()

    async def get_all_categories_with_details(self) -> list[tuple[int, str, int, int]]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT
                    categories.id,
                    categories.name,
                    categories.price,
                    COUNT(configs.id) AS stock_count
                FROM categories
                LEFT JOIN configs
                    ON configs.category = categories.name
                    AND configs.is_sold = 0
                GROUP BY categories.id, categories.name, categories.price
                ORDER BY categories.name
                """
            ) as cursor:
                return await cursor.fetchall()

    async def set_category_price(self, name: str, price: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO categories (name, price)
                VALUES (?, ?)
                ON CONFLICT(name) DO UPDATE SET price = excluded.price
                """,
                (name, price),
            )
            await db.commit()

    async def get_category_details(self, category_id: int) -> tuple[int, str, int, int] | None:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT
                    categories.id,
                    categories.name,
                    categories.price,
                    COUNT(configs.id) AS stock_count
                FROM categories
                LEFT JOIN configs
                    ON configs.category = categories.name
                    AND configs.is_sold = 0
                WHERE categories.id = ?
                GROUP BY categories.id, categories.name, categories.price
                """,
                (category_id,),
            ) as cursor:
                return await cursor.fetchone()

    async def get_available_config(self, category_name: str) -> tuple[int, str] | None:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT id, config_content
                FROM configs
                WHERE category = ? AND is_sold = 0
                ORDER BY id
                LIMIT 1
                """,
                (category_name,),
            ) as cursor:
                return await cursor.fetchone()

    async def complete_purchase(self, user_id: int, config_id: int, price: int) -> bool:
        await self.add_user_if_not_exists(user_id)
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute("BEGIN IMMEDIATE")

                async with db.execute(
                    "SELECT balance FROM users WHERE user_id = ?",
                    (user_id,),
                ) as cursor:
                    row = await cursor.fetchone()

                balance = row[0] if row else 0
                if balance < price:
                    await db.rollback()
                    return False

                async with db.execute(
                    "SELECT is_sold FROM configs WHERE id = ?",
                    (config_id,),
                ) as cursor:
                    config_row = await cursor.fetchone()

                if config_row is None or config_row[0] != 0:
                    await db.rollback()
                    return False

                await db.execute(
                    "UPDATE users SET balance = balance - ? WHERE user_id = ?",
                    (price, user_id),
                )
                update_cursor = await db.execute(
                    """
                    UPDATE configs
                    SET is_sold = 1, sold_to = ?, sold_at = datetime('now')
                    WHERE id = ? AND is_sold = 0
                    """,
                    (user_id, config_id),
                )
                if update_cursor.rowcount != 1:
                    await db.rollback()
                    return False

                await db.execute(
                    """
                    INSERT INTO transactions (user_id, amount, type, description, timestamp)
                    VALUES (?, ?, 'purchase', ?, datetime('now'))
                    """,
                    (user_id, price, f"purchase config_id={config_id}"),
                )

                await db.commit()
                return True
            except Exception:
                await db.rollback()
                raise

    async def add_transaction(self, user_id: int, amount: int, txn_type: str, description: str) -> None:
        await self.add_user_if_not_exists(user_id)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO transactions (user_id, amount, type, description, timestamp)
                VALUES (?, ?, ?, ?, datetime('now'))
                """,
                (user_id, amount, txn_type, description),
            )
            await db.commit()

    async def get_user_purchases(self, user_id: int) -> list[tuple[int, str, str, str]]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT id, category, config_content, COALESCE(sold_at, datetime('now'))
                FROM configs
                WHERE is_sold = 1 AND sold_to = ?
                ORDER BY sold_at DESC, id DESC
                """,
                (user_id,),
            ) as cursor:
                return await cursor.fetchall()

    async def get_admin_stats(self) -> dict[str, int]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM users") as cursor:
                users_count_row = await cursor.fetchone()
            async with db.execute(
                "SELECT COUNT(*) FROM users WHERE referred_by IS NOT NULL"
            ) as cursor:
                referral_count_row = await cursor.fetchone()

            # If a dedicated purchases table exists, prefer it. Otherwise fallback to transactions.
            async with db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='purchases'"
            ) as cursor:
                purchases_table_exists = await cursor.fetchone() is not None

            if purchases_table_exists:
                async with db.execute(
                    "SELECT COALESCE(SUM(price), 0), COUNT(*) FROM purchases"
                ) as cursor:
                    purchases_row = await cursor.fetchone()
                total_sales_amount = int(purchases_row[0]) if purchases_row else 0
                total_purchases = int(purchases_row[1]) if purchases_row else 0
            else:
                async with db.execute(
                    """
                    SELECT
                        COALESCE(SUM(CASE WHEN type = 'purchase' THEN amount ELSE 0 END), 0),
                        COALESCE(SUM(CASE WHEN type = 'recharge' THEN amount ELSE 0 END), 0),
                        COALESCE(SUM(CASE WHEN type = 'purchase' AND date(timestamp) = date('now') THEN 1 ELSE 0 END), 0),
                        COALESCE(SUM(CASE WHEN type = 'purchase' THEN 1 ELSE 0 END), 0)
                    FROM transactions
                    """
                ) as cursor:
                    txn_row = await cursor.fetchone()
                total_sales_amount = int(txn_row[0]) if txn_row else 0
                total_purchases = int(txn_row[3]) if txn_row else 0
                total_recharges = int(txn_row[1]) if txn_row else 0
                sales_today = int(txn_row[2]) if txn_row else 0

        total_users = int(users_count_row[0]) if users_count_row else 0
        total_referrals = int(referral_count_row[0]) if referral_count_row else 0
        result = {
            "total_users": total_users,
            "total_sales_amount": total_sales_amount,
            "total_purchases": total_purchases,
            "total_referrals": total_referrals,
        }
        if not purchases_table_exists:
            result["total_recharges"] = total_recharges
            result["sales_today"] = sales_today
        return result

    async def get_all_users_count(self) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM users") as cursor:
                row = await cursor.fetchone()
                return int(row[0]) if row else 0

    async def get_all_user_ids(self) -> list[int]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT user_id FROM users ORDER BY user_id") as cursor:
                rows = await cursor.fetchall()
                return [int(row[0]) for row in rows]

    async def get_referral_count(self, user_id: int) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM users WHERE referred_by = ?",
                (user_id,),
            ) as cursor:
                row = await cursor.fetchone()
                return int(row[0]) if row else 0

    async def get_user_purchase_history(self, user_id: int, limit: int = 5) -> list[tuple[str, str]]:
        async with aiosqlite.connect(self.db_path) as db:
            # This project stores purchase ownership on configs (sold_to), so we read history from there.
            async with db.execute(
                """
                SELECT cat.name, cfg.config_content
                FROM configs cfg
                LEFT JOIN categories cat ON cat.name = cfg.category
                WHERE cfg.sold_to = ? AND cfg.is_sold = 1
                ORDER BY cfg.sold_at DESC, cfg.id DESC
                LIMIT ?
                """,
                (user_id, limit),
            ) as cursor:
                return await cursor.fetchall()

    async def get_user_purchases_count(self, user_id: int) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM configs WHERE sold_to = ? AND is_sold = 1",
                (user_id,),
            ) as cursor:
                row = await cursor.fetchone()
                return int(row[0]) if row else 0

    async def add_new_configs(self, category_name: str, configs: list[str]) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO categories (name) VALUES (?)",
                (category_name,),
            )
            inserted_count = 0
            for config in configs:
                clean_cfg = config.strip()
                if not clean_cfg:
                    continue
                await db.execute(
                    "INSERT INTO configs (category, config_content, is_sold) VALUES (?, ?, 0)",
                    (category_name, clean_cfg),
                )
                inserted_count += 1
            await db.commit()
            return inserted_count

    async def count_active_configs_by_model(self, model: str) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT COUNT(*)
                FROM configs
                WHERE model = ? AND is_active = 1 AND is_sold = 0
                """,
                (model,),
            ) as cursor:
                row = await cursor.fetchone()
                return int(row[0]) if row else 0

    async def get_active_configs_by_model(
        self,
        model: str,
        limit: int,
        offset: int,
    ) -> list[tuple[int, str, int, str]]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT id, title, price, duration
                FROM configs
                WHERE model = ? AND is_active = 1 AND is_sold = 0
                ORDER BY id
                LIMIT ? OFFSET ?
                """,
                (model, limit, offset),
            ) as cursor:
                rows = await cursor.fetchall()
                return [(int(r[0]), str(r[1]), int(r[2]), str(r[3])) for r in rows]

    async def get_model_config_details(self, config_id: int) -> tuple[int, str, int, str, str, str] | None:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT id, title, price, duration, description, config_content
                FROM configs
                WHERE id = ? AND is_active = 1 AND is_sold = 0
                LIMIT 1
                """,
                (config_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                return (int(row[0]), str(row[1]), int(row[2]), str(row[3]), str(row[4] or ""), str(row[5]))

    async def complete_model_purchase(self, user_id: int, config_id: int) -> tuple[bool, str | None]:
        await self.add_user_if_not_exists(user_id)
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute("BEGIN IMMEDIATE")

                async with db.execute(
                    "SELECT balance FROM users WHERE user_id = ?",
                    (user_id,),
                ) as cursor:
                    user_row = await cursor.fetchone()
                balance = int(user_row[0]) if user_row else 0

                async with db.execute(
                    """
                    SELECT price, config_content, is_sold, is_active
                    FROM configs
                    WHERE id = ?
                    LIMIT 1
                    """,
                    (config_id,),
                ) as cursor:
                    config_row = await cursor.fetchone()

                if not config_row:
                    await db.rollback()
                    return False, None

                price = int(config_row[0] or 0)
                config_content = str(config_row[1])
                is_sold = int(config_row[2] or 0)
                is_active = int(config_row[3] or 0)

                if is_sold == 1 or is_active != 1:
                    await db.rollback()
                    return False, None

                if balance < price:
                    await db.rollback()
                    return False, None

                await db.execute(
                    "UPDATE users SET balance = balance - ? WHERE user_id = ?",
                    (price, user_id),
                )
                update_cursor = await db.execute(
                    """
                    UPDATE configs
                    SET is_sold = 1, sold_to = ?, sold_at = datetime('now')
                    WHERE id = ? AND is_sold = 0 AND is_active = 1
                    """,
                    (user_id, config_id),
                )
                if update_cursor.rowcount != 1:
                    await db.rollback()
                    return False, None

                await db.execute(
                    """
                    INSERT INTO transactions (user_id, amount, type, description, timestamp)
                    VALUES (?, ?, 'purchase', ?, datetime('now'))
                    """,
                    (user_id, price, f"purchase config_id={config_id}"),
                )

                await db.commit()
                return True, config_content
            except Exception:
                await db.rollback()
                raise

    async def count_admin_configs(self, model: str) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM configs WHERE model = ?",
                (model,),
            ) as cursor:
                row = await cursor.fetchone()
                return int(row[0]) if row else 0

    async def get_admin_configs(
        self,
        model: str,
        page: int,
        page_size: int,
    ) -> list[tuple[int, str, int, str, int, int]]:
        offset = max(0, (page - 1) * page_size)
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT id, title, price, duration, stock, is_active
                FROM configs
                WHERE model = ?
                ORDER BY id DESC
                LIMIT ? OFFSET ?
                """,
                (model, page_size, offset),
            ) as cursor:
                rows = await cursor.fetchall()
                return [
                    (
                        int(row[0]),
                        str(row[1] or ""),
                        int(row[2] or 0),
                        str(row[3] or "نامشخص"),
                        int(row[4] if row[4] is not None else 0),
                        int(row[5] or 0),
                    )
                    for row in rows
                ]

    async def get_config_for_admin_edit(
        self,
        config_id: int,
    ) -> tuple[int, str, str, int, str, str, int, int, str] | None:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT id, model, title, price, duration, description, stock, is_active, config_content
                FROM configs
                WHERE id = ?
                LIMIT 1
                """,
                (config_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                return (
                    int(row[0]),
                    str(row[1] or ""),
                    str(row[2] or ""),
                    int(row[3] or 0),
                    str(row[4] or "نامشخص"),
                    str(row[5] or ""),
                    int(row[6] if row[6] is not None else 0),
                    int(row[7] or 0),
                    str(row[8] or ""),
                )

    async def add_model_config(
        self,
        model: str,
        title: str,
        price: int,
        duration: str,
        description: str,
        stock: int,
        config_content: str,
    ) -> int:
        category = "Nox Plus" if model == "nox_plus" else "Nox Multi"
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO categories (name, price) VALUES (?, ?)",
                (category, price),
            )
            cursor = await db.execute(
                """
                INSERT INTO configs (
                    config_content, category, is_sold, model, title, price, duration,
                    description, stock, is_active, created_at
                )
                VALUES (?, ?, 0, ?, ?, ?, ?, ?, ?, 1, datetime('now'))
                """,
                (config_content, category, model, title, price, duration, description, stock),
            )
            await db.commit()
            return int(cursor.lastrowid)

    async def update_model_config(self, config_id: int, field: str, value: int | str) -> bool:
        allowed_fields = {"title", "price", "duration", "description", "stock", "config_content"}
        if field not in allowed_fields:
            return False
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                f"UPDATE configs SET {field} = ? WHERE id = ?",
                (value, config_id),
            )
            await db.commit()
            return cursor.rowcount == 1

    async def delete_model_config(self, config_id: int) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("DELETE FROM configs WHERE id = ?", (config_id,))
            await db.commit()
            return cursor.rowcount == 1

    async def toggle_model_config_active(self, config_id: int) -> tuple[bool, int | None]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT is_active FROM configs WHERE id = ?",
                (config_id,),
            ) as cursor:
                row = await cursor.fetchone()
            if not row:
                return False, None
            new_value = 0 if int(row[0] or 0) == 1 else 1
            cursor = await db.execute(
                "UPDATE configs SET is_active = ? WHERE id = ?",
                (new_value, config_id),
            )
            await db.commit()
            if cursor.rowcount != 1:
                return False, None
            return True, new_value
