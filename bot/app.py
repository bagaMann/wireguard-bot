import logging

from aiogram import Bot, Dispatcher, Router
from aiogram.types import BotCommand, MenuButtonCommands

from bot.config import load_settings
from bot.database import Database
from bot.handlers import register_handlers
from bot.logging import setup_logging
from bot.menu import register_menu_handlers
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

        # Новый интерфейс регистрируем первым: legacy-обработчики
        # остаются для административных операций, но не должны
        # перехватывать /start и основные действия нового меню.
        menu_router = Router()
        register_menu_handlers(menu_router, self)
        self.dispatcher.include_router(menu_router)

        router = Router()
        register_handlers(router, self)
        self.dispatcher.include_router(router)

    async def configure_telegram_menu(self):
        """Настраивает штатную кнопку Menu Telegram и единственную команду."""
        await self.bot.set_my_commands([
            BotCommand(
                command="start",
                description="Вызвать меню",
            ),
        ])

        # Штатная кнопка Menu возле поля ввода открывает список команд.
        # В нём пользователь увидит /start — «Вызвать меню».
        await self.bot.set_chat_menu_button(
            menu_button=MenuButtonCommands(),
        )

    async def run(self):
        logging.getLogger(__name__).info("Starting WireGuard Telegram Bot")
        await self.routeros.test()
        await self.configure_telegram_menu()
        await self.bot.delete_webhook(drop_pending_updates=True)
        await self.dispatcher.start_polling(self.bot)


def create_app():
    return App()
