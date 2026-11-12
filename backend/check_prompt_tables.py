import asyncio

from sqlalchemy import text

from app.db.session import engine


async def main():
    async with engine.connect() as connection:
        result = await connection.execute(
            text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)
        )

        for row in result:
            print(row[0])

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())