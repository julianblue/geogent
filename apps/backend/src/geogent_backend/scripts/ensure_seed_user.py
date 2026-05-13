"""Idempotently create the default user account from environment variables.

Designed to run on every backend startup (Railway, Docker, etc.). Reads
``SEED_USER_EMAIL`` and ``SEED_USER_PASSWORD``; if either is missing or the
user already exists, exits 0 without raising. Database connection errors are
logged but not fatal — the API process will surface them on first request.

Defaults are provided so the deployment is usable out-of-the-box; override
them in your hosting provider's environment variables for production use.
"""

from __future__ import annotations

import asyncio
import os
import sys

from geogent_backend.db.session import SessionLocal
from geogent_backend.schemas.user import UserCreate
from geogent_backend.services.auth_service import AuthError, AuthService

DEFAULT_EMAIL = "julian.blau@googlemail.com"
DEFAULT_PASSWORD = "Lena2046"


async def _run(email: str, password: str) -> int:
    async with SessionLocal() as session:
        service = AuthService(session)
        try:
            user = await service.create_user(UserCreate(email=email, password=password))
        except AuthError as exc:
            print(f"seed_user: skipped ({exc})", file=sys.stderr)
            return 0
        print(f"seed_user: created id={user.id} email={user.email}")
        return 0


def main() -> int:
    email = os.environ.get("SEED_USER_EMAIL", DEFAULT_EMAIL).strip()
    password = os.environ.get("SEED_USER_PASSWORD", DEFAULT_PASSWORD)
    if not email or not password:
        print("seed_user: SEED_USER_EMAIL/PASSWORD not set; nothing to do")
        return 0
    try:
        return asyncio.run(_run(email, password))
    except Exception as exc:
        print(f"seed_user: error {exc!r} — continuing startup", file=sys.stderr)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
