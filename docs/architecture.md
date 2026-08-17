# Архитектура

```text
Telegram
   |
   v
Debian 13 / 192.168.11.11
   |
   +-- aiogram
   +-- SQLite
   +-- WireGuard key generation
   +-- QR generation
   +-- encrypted private keys
   |
   v
RouterOS API
   |
   v
MikroTik 192.168.11.220
   |
   +-- WireGuard interface
   +-- peer #1
   +-- peer #2
   +-- peer #N
```

Debian не является WireGuard server.

Debian только управляет peer'ами MikroTik и создаёт клиентские конфигурации.
