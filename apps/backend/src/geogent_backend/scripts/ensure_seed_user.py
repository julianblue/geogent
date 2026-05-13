"""Idempotently create a login user on backend startup.

Designed to run on every backend startup (Railway, Docker, etc.). Reads
``SEED_USER_EMAIL`` and ``SEED_USER_PASSWORD`` from the environment, falling
back to ``DEFAULT_EMAIL`` / ``DEFAULT_PASSWORD`` so a fresh deployment is
usable out-of-the-box. **Override the env vars for any non-personal
deployment** — the defaults are baked into a committed file.

The script is a no-op if the user already exists, and never raises:
database / config errors are printed and swallowed so they don't block the
API process from starting (the API will surface them on first request).
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
        # Only reachable if someone explicitly sets the env var to an empty
        # string. Defaults above are non-empty, so unset → use defaults.
        print("seed_user: email or password is empty; nothing to do")
        return 0
    try:
        return asyncio.run(_run(email, password))
    except Exception as exc:
        print(f"seed_user: error {exc!r} — continuing startup", file=sys.stderr)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
