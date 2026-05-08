"""
SM3 Encryption Utilities
Equivalent to sgcc.esb.auth.core.DigestUtils
"""
import hmac as hmac_module
from gmssl import sm3, func


def _sm3_raw(data: bytes) -> bytes:
    """SM3 hash, return raw 32 bytes"""
    hex_str = sm3.sm3_hash(func.bytes_to_list(data))
    return bytes.fromhex(hex_str)


class _SM3Hash:
    """Wrapper to make gmssl SM3 compatible with Python hmac module"""

    digest_size = 32
    block_size = 64

    def __init__(self, data=b''):
        self._buffer = bytearray(data)

    def update(self, data):
        self._buffer.extend(data)

    def digest(self):
        return _sm3_raw(bytes(self._buffer))

    def hexdigest(self):
        return _sm3_raw(bytes(self._buffer)).hex()

    def copy(self):
        return _SM3Hash(bytes(self._buffer))


class DigestUtils:
    """SM3 Hash Utilities"""

    @staticmethod
    def sm3_hash(message: str) -> str:
        data = message.encode('utf-8') if isinstance(message, str) else message
        return sm3.sm3_hash(func.bytes_to_list(data))

    @staticmethod
    def sm3_with_key(key: str, data: str) -> str:
        key_bytes = key.encode('utf-8') if isinstance(key, str) else key
        msg_bytes = data.encode('utf-8') if isinstance(data, str) else data
        h = hmac_module.new(key_bytes, msg_bytes, digestmod=_SM3Hash)
        return h.hexdigest()

    @staticmethod
    def generate_sign(app_id: str, sign_key: str, timestamp: int) -> str:
        combined = f"{app_id}{sign_key}{timestamp}"
        return DigestUtils.sm3_hash(combined)

    @staticmethod
    def encrypt_sign_key(sign_key: str) -> str:
        return DigestUtils.sm3_with_key(sign_key, sign_key)
