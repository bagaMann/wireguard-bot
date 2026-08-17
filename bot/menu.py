import logging

from aiogram import Router, F
from aiogram.types import Message, FSInputFile

from bot import keyboards as kb

logger = logging.getLogger(__name__)

_last_menu = {}


async def _replace_menu(message: Message, text: str, reply_markup):
    """Удаляет нажатую reply-кнопку и предыдущий навигационный экран."""
    try:
        await message.delete()
    except Exception:
        pass

    old_id = _last_menu.get(message.chat.id)
    if old_id:
        try:
            await message.bot.delete_message(message.chat.id, old_id)
        except Exception:
            pass

    sent = await message.bot.send_message(
        message.chat.id,
        text,
        reply_markup=reply_markup,
    )
    _last_menu[message.chat.id] = sent.message_id
    return sent


async def _show_configs(message: Message, app):
    row = app.db.get_user(message.from_user.id)
    if not row or row["status"] != "approved":
        await _replace_menu(message, "Доступ не разрешён.", kb.user_reply_menu())
        return

    configs = app.db.active_configs(row["id"])
    if configs:
        text = "Ваши WireGuard-конфигурации:"
        markup = kb.user_configs(configs)
    else:
        text = "У вас пока нет активных WireGuard-конфигураций."
        markup = kb.user_main()

    await _replace_menu(message, text, markup)


async def _create_config(message: Message, app):
    row = app.db.get_user(message.from_user.id)
    if not row or row["status"] != "approved":
        await _replace_menu(message, "Доступ не разрешён.", kb.user_reply_menu())
        return

    active = app.db.count_active_configs(row["id"])
    if active >= row["qr_limit"]:
        await _replace_menu(
            message,
            f"Лимит достигнут: {active}/{row['qr_limit']}.",
            kb.user_main(),
        )
        return

    await _replace_menu(message, "Создаю WireGuard-конфигурацию...", kb.user_reply_menu())

    try:
        config_id, config, qr_path = await app.wireguard.create(
            row["id"],
            message.from_user.id,
        )
        config_row = app.db.get_config(config_id)

        await message.bot.send_photo(
            message.chat.id,
            FSInputFile(qr_path),
            caption=(
                f"✅ WireGuard #{config_id} создан.\n"
                f"Адрес: {config_row['vpn_address']}"
            ),
        )

        conf_path = app.settings.qr_dir / f"{config_id}.conf"
        conf_path.write_text(config, encoding="utf-8")
        conf_path.chmod(0o600)

        await message.bot.send_document(
            message.chat.id,
            FSInputFile(conf_path),
            caption=f"📄 Конфигурация WireGuard #{config_id}",
        )

    except Exception as exc:
        logger.exception("WireGuard creation failed")
        await message.bot.send_message(
            message.chat.id,
            f"❌ Не удалось создать конфигурацию: {exc}",
        )


async def _show_help(message: Message, app):
    row = app.db.get_user(message.from_user.id)
    text = (
        "ℹ️ Помощь\n\n"
        "📱 Мои QR-коды — просмотр существующих конфигураций.\n"
        "➕ Получить новый QR — создать дополнительную конфигурацию, если доступен лимит.\n\n"
        "QR-код можно отсканировать приложением WireGuard, а файл .conf — импортировать вручную."
    ) if row and row["status"] == "approved" else (
        "ℹ️ Помощь\n\n"
        "Для получения WireGuard-доступа сначала отправьте заявку на регистрацию."
    )
    markup = kb.admin_reply_menu() if message.from_user.id in app.settings.admin_ids else kb.user_reply_menu()
    await _replace_menu(message, text, markup)


async def _show_admin_users(message: Message, app):
    users = app.db.approved_users()
    if not users:
        text = "👥 Разрешённых пользователей нет."
        markup = kb.admin_menu()
    else:
        text = (
            "👥 Пользователи:\n\n"
            + "\n".join(
                f"🟢 {_user_identity_row(u)}\n   QR: {app.db.count_active_configs(u['id'])}/{u['qr_limit']}"
                for u in users
            )
        )
        markup = kb.admin_users(users)
    await _replace_menu(message, text, markup)


async def _show_admin_pending(message: Message, app):
    users = app.db.pending_users()
    if not users:
        await _replace_menu(message, "📨 Новых запросов нет.", kb.admin_menu())
        return

    try:
        await message.delete()
    except Exception:
        pass
    old_id = _last_menu.get(message.chat.id)
    if old_id:
        try:
            await message.bot.delete_message(message.chat.id, old_id)
        except Exception:
            pass

    for user in users:
        await message.bot.send_message(
            message.chat.id,
            _user_text(user),
            reply_markup=kb.admin_request(user["id"]),
        )

    sent = await message.bot.send_message(
        message.chat.id,
        "📨 Заявки на регистрацию показаны выше.",
        reply_markup=kb.admin_menu(),
    )
    _last_menu[message.chat.id] = sent.message_id


def register_menu_handlers(router: Router, app):
    @router.message(F.text == "📱 Мои QR-коды")
    async def menu_configs(message: Message):
        await _show_configs(message, app)

    @router.message(F.text == "➕ Получить новый QR")
    async def menu_new(message: Message):
        await _create_config(message, app)

    @router.message(F.text == "ℹ️ Помощь")
    async def menu_help(message: Message):
        await _show_help(message, app)

    @router.message(F.text == "👥 Пользователи")
    async def menu_users(message: Message):
        if message.from_user.id not in app.settings.admin_ids:
            return
        await _show_admin_users(message, app)

    @router.message(F.text == "🔔 Запросы")
    async def menu_pending(message: Message):
        if message.from_user.id not in app.settings.admin_ids:
            return
        await _show_admin_pending(message, app)


def _user_identity_row(user):
    first_name = (user["first_name"] or "").strip()
    last_name = (user["last_name"] or "").strip()
    full_name = " ".join(x for x in (first_name, last_name) if x)
    if user["username"]:
        if full_name:
            return f"{full_name} (@{user['username']}) — ID {user['telegram_id']}"
        return f"@{user['username']} — ID {user['telegram_id']}"
    return f"{full_name or 'Без имени'} — ID {user['telegram_id']}"


def _user_text(user):
    first_name = (user["first_name"] or "").strip()
    last_name = (user["last_name"] or "").strip()
    full_name = " ".join(x for x in (first_name, last_name) if x)
    username = f"@{user['username']}" if user["username"] else "нет"
    status = {
        "approved": "🟢 Разрешён",
        "pending": "🟡 Ожидает решения",
        "rejected": "🔴 Отклонён",
        "blocked": "🚫 Заблокирован",
    }.get(user["status"], user["status"])
    return (
        "👤 Пользователь\n\n"
        f"Имя: {full_name or 'Без имени'}\n"
        f"Username: {username}\n"
        f"Telegram ID: {user['telegram_id']}\n\n"
        f"Статус: {status}\n"
        f"Лимит QR: {user['qr_limit']}\n"
    )
