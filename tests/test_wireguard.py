from bot.wireguard import build_config


class Settings:
    wg_server_public_key = "SERVERKEY="
    wg_endpoint = "vpn.example.com:51820"
    wg_dns = "10.200.0.1"
    wg_client_allowed_ips = "0.0.0.0/0"
    wg_client_keepalive = 25


def test_build_config():
    text = build_config(Settings(), "CLIENTPRIVATE=", "10.200.0.2/32")
    assert "[Interface]" in text
    assert "PrivateKey = CLIENTPRIVATE=" in text
    assert "Address = 10.200.0.2/32" in text
    assert "[Peer]" in text
    assert "PublicKey = SERVERKEY=" in text
