import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from bot.menu import _create_config, _edit_user_card, _prepare_menu_screen, _send_screen

logger = logging.getLogger(__name__)


def register_cosmetic_handlers(router: Router, app):
    @router.message(F.text == "➕ Новый QR")
    async def short_new_qr(message: Message):
        await _create_config(message, app)

    @router.message(F.text == "ℹ️ Помощь")
    async def help_screen(message: Message):
        await _prepare_menu_screen(message, app)

        row = app.db.get_user(message.from_user.id)
        if row and row["status"] == "blocked":
            await _send_screen(
                message,
                "❌ Доступ к WireGuard пока не разрешён.",
            )
            return

        if message.from_user.id in app.settings.admin_ids or (
            row and row["status"] == "approved"
        ):
            await _send_screen(
                message,
                "ℹ️ Помощь\n\n"
                "📱 Мои QR — просмотр активных конфигураций.\n"
                "➕ Новый QR — создание дополнительной конфигурации, если доступен лимит.\n\n"
                "QR-код можно отсканировать приложением WireGuard, а файл .conf — импортировать вручную.",
            )
            return

        await _send_screen(
            message,
            "ℹ️ Помощь\n\n"
            "Для получения WireGuard-доступа сначала отправьте заявку на регистрацию.",
        )

    @router.callback_query(F.data.startswith("admin:limitup:"))
    async def notify_limit_up(call: CallbackQuery):
        if call.from_user.id not in app.settings.admin_ids:
            return

        user_id = int(call.data.split(":")[2])
        user = app.db.get_user_by_id(user_id)
        if not user:
            await call.answer("Пользователь не найден.", show_alert=True)
            return

        old_limit = user["qr_limit"]
        new_limit = old_limit + 1
        app.db.set_qr_limit(user_id, new_limit)
        await _edit_user_card(call, app, user_id)

        try:
            await app.bot.send_message(
                user["telegram_id"],
                "➕ Увеличен лимит WireGuard-конфигураций.\n\n"
                f"Новый лимит: {new_limit}.",
            )
        except Exception:
            logger.exception(
                "Failed to notify user %s about increased QR limit",
                user["telegram_id"],
            )

        await call.answer("Лимит увеличен.")

    @router.callback_query(F.data.startswith("admin:limitdown:"))
    async def notify_limit_down(call: CallbackQuery):
        if call.from_user.id not in app.settings.admin_ids:
            return

        user_id = int(call.data.split(":")[2])
        user = app.db.get_user_by_id(user_id)
        if not user:
            await call.answer("Пользователь не найден.", show_alert=True)
            return

        active = app.db.count_active_configs(user_id)
        old_limit = user["qr_limit"]
        new_limit = max(active, old_limit - 1)

        if new_limit == old_limit:
            await call.answer(
                "Лимит нельзя уменьшить ниже количества активных QR.",
                show_alert=True,
            )
            return

        app.db.set_qr_limit(user_id, new_limit)
        await _edit_user_card(call, app, user_id)

        try:
            await app.bot.send_message(
                user["telegram_id"],
                "➖ Уменьшен лимит WireGuard-конфигураций.\n\n"
                f"Новый лимит: {new_limit}.",
            )
        except Exception:
            logger.exception(
                "Failed to notify user %s about decreased QR limit",
                user["telegram_id"],
            )

        await call.answer("Лимит уменьшен.")
