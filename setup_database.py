import aiomysql
# from dotenv import load_dotenv
import os

class DBInterface:
    def __init__(self):
        """Initialize database configuration from environment variables."""
        # load_dotenv()  # Load environment variables from .env file
        
        self.HOST = os.getenv('DB_HOST')
        self.USER = os.getenv('DB_USER')
        self.PASS = os.getenv('DB_PASSWORD')
        self.DBASE = os.getenv('DB_NAME')
            
        self.PORT = int(os.getenv('DB_PORT', 3306))  # Default to 3306 if not provided
        self.pool = None

    async def init_pool(self):
        """Initialize the connection pool."""
        if not self.pool:  # Avoid reinitializing an existing pool
            self.pool = await aiomysql.create_pool(
                host=self.HOST,
                user=self.USER,
                password=self.PASS,
                db=self.DBASE,
                port=self.PORT,
                cursorclass=aiomysql.DictCursor,
            )
            print(self.pool)
            print("Connection pool initialized.")

    async def close_pool(self):
        """Close the connection pool."""
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()
            self.pool = None
            print("Connection pool closed.")

    async def queries(self, sql, params=None):
        """Execute SELECT queries and return results."""
        if not self.pool:
            raise RuntimeError("Connection pool is not initialized. Call `init_pool()` first.")

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                try:
                    if params:
                        await cursor.execute(sql, params)
                    else:
                        await cursor.execute(sql)
                    result = await cursor.fetchall()
                    return result
                except Exception as e:
                    print(f"Error executing query: {e}")
                    return None

    async def commands(self, sql, params=None):
        """Execute INSERT, UPDATE, DELETE commands."""
        if not self.pool:
            raise RuntimeError("Connection pool is not initialized. Call `init_pool()` first.")

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                try:
                    if params:
                        await cursor.execute(sql, params)
                    else:
                        await cursor.execute(sql)
                    await conn.commit()
                    print("Command executed successfully.")
                except Exception as e:
                    await conn.rollback()
                    print(f"Error executing command: {e}")

