import aiosqlite


class DatabaseHandler:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def initialize(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    balance INTEGER DEFAULT 0
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS configs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    config_content TEXT NOT NULL,
                    category TEXT NOT NULL,
                    is_sold INTEGER DEFAULT 0
                )
            """)
            await db.commit()

    async def add_user_if_not_exists(self, user_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO users (user_id) VALUES (?)",
                (user_id,),
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

    async def add_config(self, content: str, category: str):
        async with aiosqlite.connect(self.db_path) as db:
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
