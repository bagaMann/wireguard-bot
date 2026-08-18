import logging

from aiogram import Bot, Dispatcher, Router
from aiogram.types import BotCommand, MenuButtonCommands

from bot.config import load_settings
from bot.database import Database
from bot.handlers import register_handlers
from bot.logging import setup_logging
from bot.menu import register_menu_handlers
from bot.peer_access import register_peer_access_handlers
from bot.registration import register_registration_handlers
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

        # Блокировку/разблокировку регистрируем раньше основного меню:
        # эти обработчики синхронно меняют состояние WireGuard peers
        # в RouterOS и только после успеха меняют статус пользователя в БД.
        peer_access_router = Router()
        register_peer_access_handlers(peer_access_router, self)
        self.dispatcher.include_router(peer_access_router)

        # Новый интерфейс регистрируем перед legacy-обработчиками.
        menu_router = Router()
        register_menu_handlers(menu_router, self)
        self.dispatcher.include_router(menu_router)

        # Регистрацию держим отдельным роутером перед legacy handlers.
        # Это исправляет первый запрос: новый пользователь после INSERT
        # сразу имеет status='pending', поэтому старый обработчик ошибочно
        # считал первую заявку повторной и не уведомлял администратора.
        registration_router = Router()
        register_registration_handlers(registration_router, self)
        self.dispatcher.include_router(registration_router)

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
