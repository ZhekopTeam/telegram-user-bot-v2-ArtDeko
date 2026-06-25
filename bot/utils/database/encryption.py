import base64
import hashlib
from cryptography.fernet import Fernet
from config import settings


def _get_fernet() -> Fernet:
    raw = hashlib.sha256(settings.SESSION_MASTER_KEY.encode()).digest()
    key = base64.urlsafe_b64encode(raw)
    return Fernet(key)


def encrypt_session(session_string: str) -> str:
    return _get_fernet().encrypt(session_string.encode()).decode()


def decrypt_session(encrypted: str) -> str:
    return _get_fernet().decrypt(encrypted.encode()).decode()
