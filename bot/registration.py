import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot import keyboards as kb

logger = logging.getLogger(__name__)


def _user_identity(user):
    first_name = (user.first_name or "").strip()
    last_name = (user.last_name or "").strip()
    full_name = " ".join(part for part in (first_name, last_name) if part)

    if user.username:
        if full_name:
            return f"{full_name} (@{user.username})"
        return f"@{user.username}"

    return full_name or "Без имени"


def register_registration_handlers(router: Router, app):
    @router.callback_query(F.data == "reg:request")
    async def registration_request(call: CallbackQuery):
        user = call.from_user

        # Важно проверить состояние ДО upsert_pending_user().
        # Новый пользователь после INSERT сразу получает status='pending',
        # поэтому старая логика ошибочно считала первый запрос повторным.
        existing = app.db.get_user(user.id)

        if existing and existing["status"] == "approved":
            await call.answer(
                "Вы уже зарегистрированы.",
                show_alert=True,
            )
            return

        if existing and existing["status"] == "blocked":
            await call.answer(
                "Ваш доступ заблокирован администратором.",
                show_alert=True,
            )
            return

        if existing and existing["status"] == "pending":
            await call.answer(
                "Заявка уже отправлена.",
                show_alert=True,
            )
            return

        user_id = app.db.upsert_pending_user(
            user.id,
            user.username,
            user.first_name,
            user.last_name,
        )

        # После ранее отклонённой заявки разрешаем подать новую.
        # Для нового пользователя status уже 'pending'.
        if existing and existing["status"] == "rejected":
            app.db.set_status(user_id, "pending")

        try:
            await call.message.edit_text(
                "✅ Запрос на регистрацию отправлен администратору.\n\n"
                "Ожидайте подтверждения."
            )
        except Exception:
            logger.exception("Failed to update registration request message")

        text = (
            "📨 Новый запрос на регистрацию\n\n"
            f"👤 {_user_identity(user)}\n"
            f"Telegram ID: {user.id}\n"
        )

        admin_ids = tuple(app.settings.admin_ids)
        if not admin_ids:
            logger.error(
                "Registration request cannot be delivered: admin_ids is empty"
            )
            await call.answer(
                "Администратор не настроен. Обратитесь к администратору.",
                show_alert=True,
            )
            return

        delivered = False
        for admin_id in admin_ids:
            try:
                await app.bot.send_message(
                    admin_id,
                    text,
                    reply_markup=kb.admin_request(user_id),
                )
                delivered = True
            except Exception:
                logger.exception(
                    "Failed to send registration request to admin %s",
                    admin_id,
                )

        if delivered:
            await call.answer("Заявка отправлена.")
        else:
            # Заявка всё равно остаётся в status='pending', поэтому администратор
            # увидит её через пункт «Запросы», даже если личное уведомление
            # временно не удалось доставить.
            await call.answer(
                "Заявка сохранена, но уведомление администратору не доставлено.",
                show_alert=True,
            )
