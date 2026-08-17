import asyncio

from bot.app import create_app


def main() -> None:
    app = create_app()
    asyncio.run(app.run())


if __name__ == "__main__":
    main()
