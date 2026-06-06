import re
from datetime import datetime, timedelta, timezone

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
                CREATE TABLE IF NOT EXISTS payment_settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    card_number TEXT NOT NULL DEFAULT '',
                    card_holder_name TEXT NOT NULL DEFAULT ''
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS recharge_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    username TEXT,
                    amount INTEGER NOT NULL,
                    receipt_file_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending'
                        CHECK(status IN ('pending', 'approved', 'rejected')),
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS sales (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    username TEXT,
                    config_id INTEGER,
                    model TEXT,
                    title TEXT,
                    price INTEGER,
                    purchased_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS config_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    config_id INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    is_used INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_transactions_user_time
                ON transactions(user_id, timestamp)
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_recharge_requests_status_created
                ON recharge_requests(status, created_at DESC)
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_recharge_requests_user
                ON recharge_requests(user_id)
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
                await db.execute("ALTER TABLE configs ADD COLUMN speed TEXT DEFAULT 'نامشخص'")
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
                    speed = COALESCE(NULLIF(TRIM(speed), ''), 'نامشخص'),
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
            await db.execute(
                """
                INSERT OR IGNORE INTO payment_settings (id, card_number, card_holder_name)
                VALUES (1, '', '')
                """
            )
            await db.execute(
                """
                INSERT OR IGNORE INTO settings (key, value)
                VALUES ('referral_reward_amount', '2000')
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

    async def update_setting(self, key: str, value: str) -> None:
        await self.set_setting(key, value)

    async def get_payment_settings(self) -> tuple[str, str]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT card_number, card_holder_name
                FROM payment_settings
                WHERE id = 1
                LIMIT 1
                """
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return "", ""
                return str(row[0] or ""), str(row[1] or "")

    async def set_payment_card_number(self, card_number: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO payment_settings (id, card_number, card_holder_name)
                VALUES (1, ?, '')
                ON CONFLICT(id) DO UPDATE SET card_number = excluded.card_number
                """,
                (card_number,),
            )
            await db.commit()

    async def set_payment_card_holder_name(self, card_holder_name: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO payment_settings (id, card_number, card_holder_name)
                VALUES (1, '', ?)
                ON CONFLICT(id) DO UPDATE SET card_holder_name = excluded.card_holder_name
                """,
                (card_holder_name,),
            )
            await db.commit()

    async def create_recharge_request(
        self,
        user_id: int,
        username: str | None,
        amount: int,
        receipt_file_id: str,
    ) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO recharge_requests (user_id, username, amount, receipt_file_id, status, created_at)
                VALUES (?, ?, ?, ?, 'pending', datetime('now'))
                """,
                (user_id, username, amount, receipt_file_id),
            )
            await db.commit()
            return int(cursor.lastrowid)

    async def get_recharge_request(
        self,
        request_id: int,
    ) -> tuple[int, int, str | None, int, str, str, str] | None:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT id, user_id, username, amount, receipt_file_id, status, created_at
                FROM recharge_requests
                WHERE id = ?
                LIMIT 1
                """,
                (request_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                return (
                    int(row[0]),
                    int(row[1]),
                    str(row[2]) if row[2] is not None else None,
                    int(row[3]),
                    str(row[4]),
                    str(row[5]),
                    str(row[6]),
                )

    async def approve_recharge_request(
        self,
        request_id: int,
        approved_amount: int | None = None,
    ) -> tuple[bool, int | None, int | None]:
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute("BEGIN IMMEDIATE")
                async with db.execute(
                    "SELECT user_id, amount, status FROM recharge_requests WHERE id = ?",
                    (request_id,),
                ) as cursor:
                    row = await cursor.fetchone()
                if not row:
                    await db.rollback()
                    return False, None, None

                user_id = int(row[0])
                request_amount = int(row[1])
                status = str(row[2] or "")
                if status != "pending":
                    await db.rollback()
                    return False, user_id, request_amount

                amount = int(approved_amount) if approved_amount is not None else request_amount
                if amount <= 0:
                    await db.rollback()
                    return False, user_id, request_amount

                await db.execute(
                    "INSERT OR IGNORE INTO users (user_id) VALUES (?)",
                    (user_id,),
                )
                await db.execute(
                    "UPDATE users SET balance = balance + ? WHERE user_id = ?",
                    (amount, user_id),
                )
                await db.execute(
                    """
                    UPDATE recharge_requests
                    SET status = 'approved', amount = ?
                    WHERE id = ? AND status = 'pending'
                    """,
                    (amount, request_id),
                )
                await db.execute(
                    """
                    INSERT INTO transactions (user_id, amount, type, description, timestamp)
                    VALUES (?, ?, 'recharge', ?, datetime('now'))
                    """,
                    (user_id, amount, f"recharge request approved id={request_id}"),
                )
                await db.commit()
                return True, user_id, amount
            except Exception:
                await db.rollback()
                raise

    async def reject_recharge_request(self, request_id: int) -> tuple[bool, int | None]:
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute("BEGIN IMMEDIATE")
                async with db.execute(
                    "SELECT user_id, status FROM recharge_requests WHERE id = ?",
                    (request_id,),
                ) as cursor:
                    row = await cursor.fetchone()
                if not row:
                    await db.rollback()
                    return False, None

                user_id = int(row[0])
                status = str(row[1] or "")
                if status != "pending":
                    await db.rollback()
                    return False, user_id

                await db.execute(
                    """
                    UPDATE recharge_requests
                    SET status = 'rejected'
                    WHERE id = ? AND status = 'pending'
                    """,
                    (request_id,),
                )
                await db.commit()
                return True, user_id
            except Exception:
                await db.rollback()
                raise

    async def get_recharge_requests(
        self,
        status: str | None = None,
        user_id: int | None = None,
        username: str | None = None,
        page: int = 1,
        limit: int = 10,
    ) -> list[tuple[int, int, str | None, int, str, str, str]]:
        filters: list[str] = []
        params: list[object] = []
        if status and status in {"pending", "approved", "rejected"}:
            filters.append("status = ?")
            params.append(status)
        if user_id is not None:
            filters.append("user_id = ?")
            params.append(user_id)
        if username:
            filters.append("lower(COALESCE(username, '')) LIKE ?")
            params.append(f"%{username.lower()}%")

        where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""
        safe_limit = max(1, limit)
        safe_page = max(1, page)
        offset = (safe_page - 1) * safe_limit

        query = f"""
            SELECT id, user_id, username, amount, receipt_file_id, status, created_at
            FROM recharge_requests
            {where_sql}
            ORDER BY datetime(created_at) DESC, id DESC
            LIMIT ? OFFSET ?
        """
        params.extend([safe_limit, offset])

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(query, tuple(params)) as cursor:
                rows = await cursor.fetchall()
                return [
                    (
                        int(row[0]),
                        int(row[1]),
                        str(row[2]) if row[2] is not None else None,
                        int(row[3]),
                        str(row[4]),
                        str(row[5]),
                        str(row[6]),
                    )
                    for row in rows
                ]

    async def count_recharge_requests(
        self,
        status: str | None = None,
        user_id: int | None = None,
        username: str | None = None,
    ) -> int:
        filters: list[str] = []
        params: list[object] = []
        if status and status in {"pending", "approved", "rejected"}:
            filters.append("status = ?")
            params.append(status)
        if user_id is not None:
            filters.append("user_id = ?")
            params.append(user_id)
        if username:
            filters.append("lower(COALESCE(username, '')) LIKE ?")
            params.append(f"%{username.lower()}%")

        where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""
        query = f"SELECT COUNT(*) FROM recharge_requests {where_sql}"
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(query, tuple(params)) as cursor:
                row = await cursor.fetchone()
                return int(row[0]) if row else 0

    async def get_pending_recharge_count(self) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM recharge_requests WHERE status = 'pending'"
            ) as cursor:
                row = await cursor.fetchone()
                return int(row[0]) if row else 0

    async def get_recharge_stats_today_and_total(self) -> dict[str, int]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN status = 'approved' AND date(created_at) = date('now') THEN amount ELSE 0 END), 0),
                    COALESCE(SUM(CASE WHEN status = 'approved' AND date(created_at) = date('now') THEN 1 ELSE 0 END), 0),
                    COALESCE(SUM(CASE WHEN status = 'approved' THEN amount ELSE 0 END), 0),
                    COALESCE(SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END), 0)
                FROM recharge_requests
                """
            ) as cursor:
                row = await cursor.fetchone()
                return {
                    "today_amount": int(row[0]) if row else 0,
                    "today_count": int(row[1]) if row else 0,
                    "total_amount": int(row[2]) if row else 0,
                    "total_count": int(row[3]) if row else 0,
                }

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
                WHERE sold_to = ?
                ORDER BY sold_at DESC, id DESC
                """,
                (user_id,),
            ) as cursor:
                return await cursor.fetchall()

    async def get_user_services(self, user_id: int) -> list[dict[str, object]]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT id, title, category, config_content, duration, sold_at
                FROM configs
                WHERE sold_to = ?
                ORDER BY sold_at DESC, id DESC
                """,
                (user_id,),
            ) as cursor:
                rows = await cursor.fetchall()

        now = datetime.now(timezone.utc)
        services: list[dict[str, object]] = []
        for row in rows:
            config_id = int(row[0])
            title = str(row[1] or row[2] or "سرویس")
            config_content = str(row[3] or "")
            duration_text = str(row[4] or "")
            sold_at_text = str(row[5] or "")

            expires_at = "نامشخص"
            days = self._extract_duration_days(duration_text)
            sold_at_dt: datetime | None = None
            if sold_at_text:
                try:
                    sold_at_dt = datetime.fromisoformat(sold_at_text.replace(" ", "T")).replace(
                        tzinfo=timezone.utc
                    )
                except ValueError:
                    sold_at_dt = None
            if sold_at_dt and days is not None and days > 0:
                expiry_dt = sold_at_dt + timedelta(days=days)
                if expiry_dt < now:
                    continue
                expires_at = expiry_dt.strftime("%Y-%m-%d %H:%M:%S UTC")

            services.append(
                {
                    "id": config_id,
                    "name": title,
                    "config_link": config_content,
                    "expires_at": expires_at,
                }
            )
        return services

    @staticmethod
    def _extract_duration_days(duration: str) -> int | None:
        normalized = (duration or "").strip().lower()
        if not normalized:
            return None
        match = re.search(r"(\d+)", normalized)
        if not match:
            return None
        value = int(match.group(1))
        if "ماه" in normalized:
            return value * 30
        if "سال" in normalized:
            return value * 365
        return value

    async def get_user_active_services(
        self,
        user_id: int,
    ) -> list[tuple[int, str, str, str]]:
        services = await self.get_user_services(user_id)
        return [
            (
                int(service["id"]),
                str(service["name"]),
                str(service["config_link"]),
                str(service["expires_at"]),
            )
            for service in services
        ]

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
                WHERE cfg.sold_to = ?
                ORDER BY cfg.sold_at DESC, cfg.id DESC
                LIMIT ?
                """,
                (user_id, limit),
            ) as cursor:
                return await cursor.fetchall()

    async def get_user_purchases_count(self, user_id: int) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM configs WHERE sold_to = ?",
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

    async def log_sale(
        self,
        user_id: int,
        username: str | None,
        config_id: int,
        model: str,
        title: str,
        price: int,
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO sales (user_id, username, config_id, model, title, price)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, username, config_id, model, title, price),
            )
            await db.commit()

    async def get_total_sales_amount(self) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT COALESCE(SUM(price), 0) FROM sales"
            ) as cursor:
                row = await cursor.fetchone()
                return int(row[0]) if row else 0

    async def get_today_sales_count(self) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM sales WHERE date(purchased_at) = date('now')"
            ) as cursor:
                row = await cursor.fetchone()
                return int(row[0]) if row else 0

    async def get_today_sales_amount(self) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT COALESCE(SUM(price), 0) FROM sales WHERE date(purchased_at) = date('now')"
            ) as cursor:
                row = await cursor.fetchone()
                return int(row[0]) if row else 0

    async def get_latest_sales(self, limit: int = 10) -> list[tuple[str | None, str, str, int, str]]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT username, model, title, price, purchased_at
                FROM sales
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [
                    (
                        str(row[0]) if row[0] is not None else None,
                        str(row[1] or ""),
                        str(row[2] or ""),
                        int(row[3] or 0),
                        str(row[4] or ""),
                    )
                    for row in rows
                ]

    async def count_active_configs_by_model(self, model: str) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT COUNT(*)
                FROM configs
                WHERE model = ? AND is_active = 1 AND is_sold = 0 AND (stock = -1 OR stock > 0)
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
                WHERE model = ? AND is_active = 1 AND is_sold = 0 AND (stock = -1 OR stock > 0)
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
                WHERE id = ? AND is_active = 1 AND (stock = -1 OR stock > 0)
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
                    SELECT price, config_content, is_sold, is_active, stock
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
                default_config_content = str(config_row[1] or "")
                is_sold = int(config_row[2] or 0)
                is_active = int(config_row[3] or 0)
                stock = int(config_row[4] if config_row[4] is not None else 0)

                if is_sold == 1 or is_active != 1:
                    await db.rollback()
                    return False, None
                if stock == 0:
                    await db.rollback()
                    return False, None

                if balance < price:
                    await db.rollback()
                    return False, None

                selected_item_id: int | None = None
                config_content = default_config_content
                async with db.execute(
                    """
                    SELECT id, content
                    FROM config_items
                    WHERE config_id = ? AND is_used = 0
                    ORDER BY id
                    LIMIT 1
                    """,
                    (config_id,),
                ) as cursor:
                    item_row = await cursor.fetchone()
                if item_row is not None:
                    selected_item_id = int(item_row[0])
                    config_content = str(item_row[1])
                elif stock > 0:
                    await db.rollback()
                    return False, None

                await db.execute(
                    "UPDATE users SET balance = balance - ? WHERE user_id = ?",
                    (price, user_id),
                )
                if selected_item_id is not None:
                    item_update = await db.execute(
                        """
                        UPDATE config_items
                        SET is_used = 1
                        WHERE id = ? AND is_used = 0
                        """,
                        (selected_item_id,),
                    )
                    if item_update.rowcount != 1:
                        await db.rollback()
                        return False, None
                update_cursor = await db.execute(
                    """
                    UPDATE configs
                    SET
                        is_sold = CASE
                            WHEN stock = -1 THEN 0
                            WHEN stock > 1 THEN 0
                            ELSE 1
                        END,
                        sold_to = ?,
                        sold_at = datetime('now'),
                        stock = CASE
                            WHEN stock = -1 THEN -1
                            WHEN stock > 0 THEN stock - 1
                            ELSE 0
                        END
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

    async def get_model_config_purchase_snapshot(
        self,
        config_id: int,
    ) -> tuple[int, str, int, str, str, str, str, int, int, int] | None:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT id, title, price, duration, description, config_content, model, stock, is_active, is_sold
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
                    int(row[2] or 0),
                    str(row[3] or "نامشخص"),
                    str(row[4] or ""),
                    str(row[5] or ""),
                    str(row[6] or ""),
                    int(row[7] if row[7] is not None else 0),
                    int(row[8] or 0),
                    int(row[9] or 0),
                )

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
    ) -> tuple[int, str, str, int, str, str, str, int, int, str] | None:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT id, model, title, price, duration, speed, description, stock, is_active, config_content
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
                    str(row[6] or ""),
                    int(row[7] if row[7] is not None else 0),
                    int(row[8] or 0),
                    str(row[9] or ""),
                )

    async def add_model_config(
        self,
        model: str,
        title: str,
        price: int,
        duration: str,
        speed: str,
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
                    speed, description, stock, is_active, created_at
                )
                VALUES (?, ?, 0, ?, ?, ?, ?, ?, ?, ?, 1, datetime('now'))
                """,
                (config_content, category, model, title, price, duration, speed, description, stock),
            )
            await db.commit()
            return int(cursor.lastrowid)

    async def add_model_config_with_items(
        self,
        model: str,
        title: str,
        price: int,
        duration: str,
        speed: str,
        description: str,
        stock: int,
        config_items: list[str],
    ) -> int:
        category = "Nox Plus" if model == "nox_plus" else "Nox Multi"
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("BEGIN IMMEDIATE")
            try:
                await db.execute(
                    "INSERT OR IGNORE INTO categories (name, price) VALUES (?, ?)",
                    (category, price),
                )
                cursor = await db.execute(
                    """
                    INSERT INTO configs (
                        config_content, category, is_sold, model, title, price, duration,
                        speed, description, stock, is_active, created_at
                    )
                    VALUES (?, ?, 0, ?, ?, ?, ?, ?, ?, ?, 1, datetime('now'))
                    """,
                    ("", category, model, title, price, duration, speed, description, stock),
                )
                config_id = int(cursor.lastrowid)
                for item in config_items:
                    await db.execute(
                        """
                        INSERT INTO config_items (config_id, content, is_used)
                        VALUES (?, ?, 0)
                        """,
                        (config_id, item),
                    )
                await db.commit()
                return config_id
            except Exception:
                await db.rollback()
                raise

    async def update_model_config(self, config_id: int, field: str, value: int | str) -> bool:
        allowed_fields = {"title", "price", "duration", "speed", "description", "stock", "config_content"}
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
