"""
Script to create an initial human user with a password for local testing.
"""

import asyncio
import argparse
import sys
from typing import Optional

from passlib.context import CryptContext
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Add the project root to sys.path to allow importing from 'app'
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.models.user import User
from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


async def create_user(email: str, password: str):
    engine = create_async_engine(str(settings.database_url))
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Check if user already exists
        result = await session.execute(select(User).where(User.email == email))
        existing_user = result.scalar_one_or_none()

        if existing_user:
            print(f"User with email {email} already exists.")
            return

        # Create user
        user = User(
            email=email,
            type="human",
            password_hash=get_password_hash(password)
        )
        session.add(user)
        await session.commit()
        print(f"Successfully created user: {email}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create a local admin user.")
    parser.add_argument("--email", required=True, help="Email address for the user")
    parser.add_argument("--password", required=True, help="Password for the user")

    args = parser.parse_args()

    asyncio.run(create_user(args.email, args.password))
