"""Create a user account from the CLI.

Usage:
    uv run python -m geogent_backend.scripts.seed_user --email a@b.com --password secret123
"""

import argparse
import asyncio
import sys

from geogent_backend.db.session import SessionLocal
from geogent_backend.schemas.user import UserCreate
from geogent_backend.services.auth_service import AuthError, AuthService


async def _create(email: str, password: str) -> int:
    async with SessionLocal() as session:
        try:
            user = await AuthService(session).create_user(
                UserCreate(email=email, password=password)
            )
        except AuthError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    print(f"created user id={user.id} email={user.email}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a geogent user account.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    args = parser.parse_args()
    return asyncio.run(_create(args.email, args.password))


if __name__ == "__main__":
    raise SystemExit(main())
