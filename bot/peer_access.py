import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot import keyboards as kb

logger = logging.getLogger(__name__)


def _user_text(user):
    first_name = (user["first_name"] or "").strip()
    last_name = (user["last_name"] or "").strip()
    full_name = " ".join(x for x in (first_name, last_name) if x)
    username = f"@{user['username']}" if user["username"] else "нет"
    status = {
        "approved": "🟢 Разрешён",
        "pending": "🟡 Ожидает решения",
        "rejected": "🔴 Отклонён",
        "blocked": "🔴 Заблокирован",
    }.get(user["status"], user["status"])

    return (
        "👤 Пользователь\n\n"
        f"Имя: {full_name or 'Без имени'}\n"
        f"Username: {username}\n"
        f"Telegram ID: {user['telegram_id']}\n\n"
        f"Статус: {status}\n"
        f"Лимит QR: {user['qr_limit']}\n"
    )


async def _set_user_peers_disabled(app, user_id: int, disabled: bool):
    """
    Изменить состояние всех активных WireGuard peers пользователя.

    Если изменение одного peer завершается ошибкой, уже изменённые peers
    возвращаются в исходное состояние. Статус пользователя в БД при этом
    вызывающий код не меняет.
    """
    configs = app.db.active_configs(user_id)
    changed_peer_ids = []

    try:
        for config in configs:
            peer_id = config["routeros_peer_id"]
            if not peer_id:
                continue

            await app.routeros.set_peer_disabled(peer_id, disabled)
            changed_peer_ids.append(peer_id)
    except Exception:
        rollback_disabled = not disabled
        for peer_id in reversed(changed_peer_ids):
            try:
                await app.routeros.set_peer_disabled(peer_id, rollback_disabled)
            except Exception:
                logger.exception(
                    "Failed to roll back WireGuard peer %s after access-state error",
                    peer_id,
                )
        raise


def register_peer_access_handlers(router: Router, app):
    @router.callback_query(F.data.startswith("admin:block:"))
    async def block_user(call: CallbackQuery):
        if call.from_user.id not in app.settings.admin_ids:
            return

        user_id = int(call.data.split(":")[2])
        user = app.db.get_user_by_id(user_id)
        if not user:
            await call.answer("Пользователь не найден.", show_alert=True)
            return

        if user["telegram_id"] in app.settings.admin_ids:
            await call.answer("Администратора нельзя заблокировать.", show_alert=True)
            return

        if user["status"] == "blocked":
            await call.answer("Пользователь уже заблокирован.", show_alert=True)
            return

        try:
            await _set_user_peers_disabled(app, user_id, True)
        except Exception as exc:
            logger.exception("Failed to disable WireGuard peers for user %s", user_id)
            await call.answer(
                f"Не удалось отключить WireGuard peers: {exc}",
                show_alert=True,
            )
            return

        app.db.set_status(user_id, "blocked")
        user = app.db.get_user_by_id(user_id)

        await call.message.edit_text(
            _user_text(user),
            reply_markup=kb.admin_user(user_id, user["status"]),
        )

        try:
            await app.bot.send_message(
                user["telegram_id"],
                "🚫 Ваш доступ заблокирован администратором.\n\n"
                "Все ваши WireGuard-подключения временно отключены.",
            )
        except Exception:
            logger.exception("Failed to notify blocked user %s", user["telegram_id"])

        await call.answer("Пользователь и его WireGuard peers заблокированы.")

    @router.callback_query(F.data.startswith("admin:unblock:"))
    async def unblock_user(call: CallbackQuery):
        if call.from_user.id not in app.settings.admin_ids:
            return

        user_id = int(call.data.split(":")[2])
        user = app.db.get_user_by_id(user_id)
        if not user:
            await call.answer("Пользователь не найден.", show_alert=True)
            return

        if user["status"] != "blocked":
            await call.answer("Пользователь не заблокирован.", show_alert=True)
            return

        try:
            await _set_user_peers_disabled(app, user_id, False)
        except Exception as exc:
            logger.exception("Failed to enable WireGuard peers for user %s", user_id)
            await call.answer(
                f"Не удалось включить WireGuard peers: {exc}",
                show_alert=True,
            )
            return

        app.db.set_status(user_id, "approved")
        user = app.db.get_user_by_id(user_id)

        await call.message.edit_text(
            _user_text(user),
            reply_markup=kb.admin_user(user_id, user["status"]),
        )

        try:
            await app.bot.send_message(
                user["telegram_id"],
                "✅ Ваш доступ к WireGuard-боту восстановлен.\n\n"
                "Ваши WireGuard-подключения снова активны.",
                reply_markup=kb.user_reply_menu(),
            )
        except Exception:
            logger.exception("Failed to notify unblocked user %s", user["telegram_id"])

        await call.answer("Пользователь и его WireGuard peers разблокированы.")
