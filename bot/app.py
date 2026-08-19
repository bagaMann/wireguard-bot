import logging

from aiogram import Bot, Dispatcher, Router
from aiogram.types import BotCommand, MenuButtonCommands

from bot.config import load_settings
from bot.cosmetic import register_cosmetic_handlers
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

        # Небольшие UI-исправления держим перед основным меню, чтобы
        # короткая кнопка «Новый QR» и корректная помощь для blocked
        # обрабатывались без изменения стабильной навигации.
        cosmetic_router = Router()
        register_cosmetic_handlers(cosmetic_router, self)
        self.dispatcher.include_router(cosmetic_router)

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

    async def ensure_admin_users(self):
        """Создать/разрешить администраторов в новой пустой базе данных.

        ADMIN_IDS даёт административное меню, но пользовательские QR-функции
        используют запись из таблицы users. На чистой установке такой записи
        ещё нет, поэтому администратор раньше видел «Доступ не разрешён».
        """
        log = logging.getLogger(__name__)

        for telegram_id in self.settings.admin_ids:
            username = None
            first_name = "Administrator"
            last_name = None

            try:
                chat = await self.bot.get_chat(telegram_id)
                username = getattr(chat, "username", None)
                first_name = getattr(chat, "first_name", None) or first_name
                last_name = getattr(chat, "last_name", None)
            except Exception as exc:
                # Даже если Telegram временно не дал данные профиля,
                # администратор всё равно должен быть создан в БД.
                log.warning(
                    "Could not read Telegram profile for admin %s: %s",
                    telegram_id,
                    exc,
                )

            user_id = self.db.upsert_pending_user(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
            )
            user = self.db.get_user_by_id(user_id)

            if not user or user["status"] != "approved":
                self.db.approve_user(
                    user_id,
                    telegram_id,
                    self.settings.default_qr_limit,
                )
                log.info("Administrator %s provisioned in database", telegram_id)

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
        await self.ensure_admin_users()
        await self.configure_telegram_menu()
        await self.bot.delete_webhook(drop_pending_updates=True)
        await self.dispatcher.start_polling(self.bot)


def create_app():
    return App()
