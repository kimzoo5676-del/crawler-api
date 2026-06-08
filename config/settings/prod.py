from .base import *

DEBUG = False

DATABASES = {
    "default": env.db(),
}


# --- HTTPS / behind Nginx proxy (Closes #12) ---
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
