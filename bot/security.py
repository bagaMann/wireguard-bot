from cryptography.fernet import Fernet


class SecretBox:
    def __init__(self, key: bytes):
        self._fernet = Fernet(key)

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        return self._fernet.decrypt(value.encode()).decode()


def generate_fernet_key() -> str:
    return Fernet.generate_key().decode()
