"""
Token-aware HTTP client: token acquisition (ESB / OAuth2 / Redis / static),
token injection, authenticated requests with automatic retry and prefix fallback.
"""
import json
import time
import requests
import redis as redis_lib

from .sm3_utils import DigestUtils

AUTH_RETRY_CODES = {401, 403, 420}


class TokenProvider:
    """Manages token acquisition based on configured strategy."""

    def __init__(self, token_config):
        self.config = token_config
        self.strategy = token_config.get("strategy", "static")
        self.header_name = token_config.get("header_name", "x-token")
        self.header_prefix = token_config.get("header_prefix", "")
        self.header_prefix_fallbacks = token_config.get("header_prefix_fallbacks", ["Bearer"])
        self._token = None
        self._redis_client = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_token(self):
        """Return a valid token (may be cached / from Redis)."""
        if self.strategy == "none":
            return None
        elif self.strategy == "esb":
            return self._get_esb_token()
        elif self.strategy == "oauth2":
            return self._get_oauth2_token()
        elif self.strategy == "redis":
            return self._get_redis_token()
        else:
            return self.config.get("static", {}).get("value", "")

    def force_refresh(self):
        """Force-fetch a new token (ignoring cache)."""
        if self.strategy == "esb":
            return self._get_esb_token(force=True)
        elif self.strategy == "oauth2":
            return self._get_oauth2_token(force=True)
        return self.get_token()

    def inject_token(self, headers, prefix=None):
        """Add token header to the request headers dict."""
        token = self.get_token()
        if not token:
            return
        p = (prefix if prefix is not None else self.header_prefix).strip()
        headers[self.header_name] = f"{p} {token}" if p else token

    def request(self, url, method="POST", body=None, headers=None, timeout=30):
        """
        Send an HTTP request with automatic token injection (when strategy is not 'none').

        On auth failure (401/403/420):
          1. force-refresh token and retry
          2. try each fallback prefix
        Returns (status_code, parsed_json | None).
        """
        base_headers = dict(headers or {})
        if "Content-Type" not in base_headers:
            base_headers["Content-Type"] = "application/json"

        # No auth: just send the request directly
        if self.strategy == "none":
            return self._raw_request(url, method, base_headers, body, timeout)

        # Step 1: primary prefix
        h = dict(base_headers)
        self.inject_token(h)
        status_code, json_data = self._raw_request(url, method, h, body, timeout)
        if status_code not in AUTH_RETRY_CODES:
            return status_code, json_data

        # Step 2: force-refresh token + retry
        print(f"  [fetch] got {status_code}, refreshing token and retrying...")
        self.force_refresh()
        h = dict(base_headers)
        self.inject_token(h)
        status_code, json_data = self._raw_request(url, method, h, body, timeout)
        if status_code not in AUTH_RETRY_CODES:
            return status_code, json_data

        # Step 3: fallback prefixes
        for fallback in self.header_prefix_fallbacks:
            if fallback == self.header_prefix:
                continue
            print(f"  [fetch] still {status_code}, retrying with prefix='{fallback}'...")
            h = dict(base_headers)
            self.inject_token(h, prefix=fallback)
            status_code, json_data = self._raw_request(url, method, h, body, timeout)
            if status_code not in AUTH_RETRY_CODES:
                print(f"  [fetch] success with prefix='{fallback}'")
                return status_code, json_data

        return status_code, None

    # ------------------------------------------------------------------
    # Internal: raw HTTP
    # ------------------------------------------------------------------

    @staticmethod
    def _raw_request(url, method, headers, body, timeout):
        """Execute a single HTTP request. Returns (status_code, parsed_json | None)."""
        resp = requests.request(
            method=method.upper(),
            url=url,
            headers=headers,
            json=body if body else None,
            timeout=timeout,
        )

        if resp.status_code in AUTH_RETRY_CODES:
            return resp.status_code, None

        resp.raise_for_status()
        return resp.status_code, resp.json()

    # ------------------------------------------------------------------
    # ESB strategy
    # ------------------------------------------------------------------

    def _get_esb_token(self, force=False):
        esb_cfg = self.config.get("esb", {})
        redis_cfg = esb_cfg.get("redis", {})
        cache_key = esb_cfg.get("cache_key", "esb:access_token")
        early_expire = esb_cfg.get("early_expire_seconds", 120)

        r = self._get_redis(redis_cfg)

        if not force:
            try:
                cached = r.get(cache_key)
                if cached:
                    ttl = r.ttl(cache_key)
                    if ttl and ttl > early_expire:
                        print(f"  [token] cache hit, key={cache_key}, ttl={ttl}s")
                        return cached
            except Exception:
                pass

        token_url = esb_cfg["token_url"]
        esb_app_id = esb_cfg["esb_app_id"]
        esb_sign = esb_cfg["esb_sign"]

        timestamp = int(time.time() * 1000)
        esb_sign_encrypted = DigestUtils.encrypt_sign_key(esb_sign)
        sign = DigestUtils.generate_sign(esb_app_id, esb_sign, timestamp)

        request_data = {
            "esb_appid": esb_app_id,
            "esb_sign": esb_sign_encrypted,
            "sign": sign,
            "timestamp": timestamp,
            "grant_type": "all",
        }

        print(f"  [token] requesting new token from {token_url}")
        resp = requests.post(
            token_url,
            data=json.dumps(request_data, separators=(",", ":")),
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()

        data_field = result.get("data", {})
        access_token = data_field.get("access_token")
        expires_in = data_field.get("expires_in", 7200)

        if not access_token:
            raise RuntimeError(f"Token not found in response: {result}")

        ttl = max(30, expires_in - early_expire)
        try:
            r.set(cache_key, access_token, ex=ttl)
            print(f"  [token] cached, key={cache_key}, ttl={ttl}s")
        except Exception as e:
            print(f"  [token] redis cache failed: {e}")

        return access_token

    # ------------------------------------------------------------------
    # OAuth2 strategy
    # ------------------------------------------------------------------

    def _get_oauth2_token(self, force=False):
        oauth2_cfg = self.config.get("oauth2", {})
        redis_cfg = oauth2_cfg.get("redis", {})
        cache_key = oauth2_cfg.get("cache_key", "oauth2:access_token")
        early_expire = oauth2_cfg.get("early_expire_seconds", 120)

        r = self._get_redis(redis_cfg)

        if not force:
            try:
                cached = r.get(cache_key)
                if cached:
                    ttl = r.ttl(cache_key)
                    if ttl and ttl > early_expire:
                        print(f"  [token] cache hit, key={cache_key}, ttl={ttl}s")
                        return cached
            except Exception:
                pass

        token_url = oauth2_cfg["token_url"]
        request_data = {
            "grant_type": oauth2_cfg.get("grant_type", "client_credentials"),
            "client_id": oauth2_cfg["client_id"],
            "client_secret": oauth2_cfg["client_secret"],
        }

        print(f"  [token] requesting new token from {token_url}")
        resp = requests.post(
            token_url,
            json=request_data,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()

        if result.get("status") and result.get("status") != "000000":
            raise RuntimeError(f"OAuth2 error: {result.get('message', result)}")

        access_token = result.get("access_token")
        expires_in = result.get("expires_in", 7200)

        if not access_token:
            raise RuntimeError(f"access_token not found in response: {result}")

        ttl = max(30, expires_in - early_expire)
        try:
            r.set(cache_key, access_token, ex=ttl)
            print(f"  [token] cached, key={cache_key}, ttl={ttl}s")
        except Exception as e:
            print(f"  [token] redis cache failed: {e}")

        return access_token

    # ------------------------------------------------------------------
    # Redis-only strategy
    # ------------------------------------------------------------------

    def _get_redis_token(self):
        redis_cfg = self.config.get("redis", {})
        key = redis_cfg.get("key", "esb:access_token")
        r = self._get_redis(redis_cfg)
        token = r.get(key)
        if not token:
            raise RuntimeError(f"Token not found in Redis key '{key}'")
        return token

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_redis(self, redis_cfg):
        if self._redis_client is None:
            self._redis_client = redis_lib.Redis(
                host=redis_cfg.get("host", "127.0.0.1"),
                port=redis_cfg.get("port", 6379),
                password=redis_cfg.get("password") or None,
                db=redis_cfg.get("db", 0),
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
            )
        return self._redis_client
