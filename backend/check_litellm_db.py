import asyncio

from prisma import Prisma


async def main():
    db = Prisma()

    try:
        await db.connect()
        print("PRISMA_CONNECTED")

        result = await db.query_raw("SELECT 1")
        print("QUERY_RESULT:", result)

    except Exception as exc:
        print("PRISMA_ERROR:", repr(exc))

    finally:
        if db.is_connected():
            await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())