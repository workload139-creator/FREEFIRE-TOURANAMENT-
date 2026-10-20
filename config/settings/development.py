from .base import *

DEBUG = True

if not SECRET_KEY:
    raise RuntimeError("Set DJANGO_SECRET_KEY in your local .env file.")
