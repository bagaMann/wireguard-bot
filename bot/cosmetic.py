from aiogram import F, Router
from aiogram.types import Message

from bot.menu import _create_config, _prepare_menu_screen, _send_screen


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
                "📱 Мои QR-коды — просмотр активных конфигураций.\n"
                "➕ Новый QR — создание дополнительной конфигурации, если доступен лимит.\n\n"
                "QR-код можно отсканировать приложением WireGuard, а файл .conf — импортировать вручную.",
            )
            return

        await _send_screen(
            message,
            "ℹ️ Помощь\n\n"
            "Для получения WireGuard-доступа сначала отправьте заявку на регистрацию.",
        )
