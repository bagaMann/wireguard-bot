from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


def user_reply_menu():
    """Постоянное меню обычного пользователя."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 WireGuard")],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def admin_reply_menu():
    """Постоянное меню администратора: пользовательский и админский режим."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="👤 Пользователь"),
                KeyboardButton(text="🔐 Администрирование"),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def user_main():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Мои QR-коды", callback_data="user:configs")],
        [InlineKeyboardButton(text="➕ Получить новый QR", callback_data="user:new")],
    ])


def registration():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Запросить регистрацию", callback_data="reg:request")],
    ])


def admin_request(user_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Разрешить", callback_data=f"admin:approve:{user_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin:reject:{user_id}"),
        ],
    ])


def user_configs(configs):
    rows = [
        [InlineKeyboardButton(
            text=f"📱 {row['name']} ({row['vpn_address']})",
            callback_data=f"user:show:{row['id']}",
        )]
        for row in configs
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="user:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def config_actions(config_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📷 Показать QR", callback_data=f"user:qr:{config_id}")],
        [InlineKeyboardButton(text="📄 Получить конфигурацию", callback_data=f"user:conf:{config_id}")],
        [InlineKeyboardButton(text="⬅️ Мои QR-коды", callback_data="user:configs")],
    ])


def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📨 Запросы", callback_data="admin:pending")],
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="admin:users")],
    ])


def admin_users(users):
    rows = [
        [InlineKeyboardButton(
            text=f"{'🟢' if u['status'] == 'approved' else '🔴'} "
                 f"{u['first_name'] or ''} @{u['username'] or 'нет'}",
            callback_data=f"admin:user:{u['id']}",
        )]
        for u in users
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_user(user_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Увеличить лимит", callback_data=f"admin:limitup:{user_id}")],
        [InlineKeyboardButton(text="➖ Уменьшить лимит", callback_data=f"admin:limitdown:{user_id}")],
        [InlineKeyboardButton(text="📱 QR-коды", callback_data=f"admin:configs:{user_id}")],
        [InlineKeyboardButton(text="🚫 Заблокировать", callback_data=f"admin:block:{user_id}")],
        [InlineKeyboardButton(text="⬅️ Пользователи", callback_data="admin:users")],
    ])


def admin_configs(configs):
    rows = [
        [InlineKeyboardButton(
            text=f"🟢 {row['name']} {row['vpn_address']}",
            callback_data=f"admin:delcfg:{row['id']}",
        )]
        for row in configs
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin:users")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
