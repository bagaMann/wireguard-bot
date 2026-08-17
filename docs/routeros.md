# MikroTik RouterOS

## WireGuard

Пример:

```routeros
/interface/wireguard
add listen-port=51820 name=wireguard1

/ip/address
add address=10.200.0.1/24 interface=wireguard1
```

Получить public key:

```routeros
/interface/wireguard/print detail
```

## API

Рекомендуется отдельный пользователь для бота.

Минимальные права следует подобрать под фактическую конфигурацию и протестировать. Для первой установки можно временно использовать отдельную учётную запись с достаточными правами, затем уменьшить набор permissions.

API должен быть доступен с Debian `192.168.11.11` до MikroTik `192.168.11.220`.

Проверить:

```bash
nc -vz 192.168.11.220 8728
```

Для API-SSL:

```bash
nc -vz 192.168.11.220 8729
```

## Firewall

Разрешите API только с IP Debian, а не из всего LAN/WAN.

Пример логики:

```routeros
/ip/service
set api address=192.168.11.11/32
```

Точную настройку firewall выполняйте согласно своей действующей политике.

## Peer

Бот создаёт примерно:

```routeros
/interface/wireguard/peers
add interface=wireguard1 \
    public-key="<CLIENT_PUBLIC_KEY>" \
    allowed-address=10.200.0.2/32 \
    comment="telegram:1234567890:wg" \
    name="wg-1234567890-1" \
    responder=yes
```

`allowed-address` каждого peer должен быть уникальным в рамках интерфейса.

## API user

Не открывайте API наружу. Ограничьте `/ip/service` и firewall так, чтобы API был доступен только Debian `192.168.11.11`.

Перед запуском бота проверьте:

```bash
nc -vz 192.168.11.220 8728
```

Если используется API-SSL:

```bash
nc -vz 192.168.11.220 8729
```
