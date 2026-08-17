import logging

from aiogram import Bot, Dispatcher, Router

from bot.config import load_settings
from bot.database import Database
from bot.handlers import register_handlers
from bot.logging import setup_logging
from bot.routeros import RouterOSClient
from bot.wireguard import WireGuardService


class App:
    def __init__(self):
        setup_logging()
        self.settings = load_settings()
        self.db = Database(self.settings.database_path)
        self.db.init()
        self.bot = Bot(self.settings.bot_token)
        self.dispatcher = Dispatcher()
        self.routeros = RouterOSClient(self.settings)
        self.wireguard = WireGuardService(
            self.settings,
            self.db,
            self.routeros,
        )

        router = Router()
        register_handlers(router, self)
        self.dispatcher.include_router(router)

    async def run(self):
        logging.getLogger(__name__).info("Starting WireGuard Telegram Bot")
        await self.routeros.test()
        await self.bot.delete_webhook(drop_pending_updates=True)
        await self.dispatcher.start_polling(self.bot)

def create_app():
    return App()
