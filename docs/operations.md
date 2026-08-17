# Эксплуатация

## Статус

```bash
systemctl status wireguard-bot
```

## Логи

```bash
journalctl -u wireguard-bot -f
```

## Перезапуск

```bash
systemctl restart wireguard-bot
```

## База

```text
/opt/wireguard-bot/data/bot.db
```

## QR

```text
/opt/wireguard-bot/data/qr/
```

QR и временные `.conf` являются секретными данными.

## Резервное копирование

Нужно сохранять:

- `data/bot.db`;
- `.env`.

Особенно важно сохранить `APP_FERNET_KEY`: без него существующие приватные ключи из БД расшифровать невозможно.
