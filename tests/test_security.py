from bot.security import SecretBox, generate_fernet_key


def test_fernet_roundtrip():
    box = SecretBox(generate_fernet_key().encode())
    value = "private-key-test"
    encrypted = box.encrypt(value)
    assert encrypted != value
    assert box.decrypt(encrypted) == value
