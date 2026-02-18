"""
Script to create an initial human user with a password for local testing.
"""

import asyncio
import argparse
import sys
from typing import Optional

import uuid
from passlib.context import CryptContext
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Add the project root to sys.path to allow importing from 'app'
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.models.user import User
from app.models.organization import Organization
from app.models.user_org import UserOrg
from app.core.config import get_settings

settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


async def create_user(email: str, password: str):
    engine = create_async_engine(str(settings.database_url))
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # 1. Ensure Default Organization exists
        result = await session.execute(select(Organization).where(Organization.slug == "default"))
        org = result.scalar_one_or_none()
        
        if not org:
            org = Organization(
                id=uuid.uuid4(),
                name="Default Organization",
                slug="default",
                status="active",
                settings={}
            )
            session.add(org)
            print("Created default organization.")
        
        # 2. Check if user already exists
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user:
            # Create user
            user = User(
                id=uuid.uuid4(),
                email=email,
                type="human",
                password_hash=get_password_hash(password)
            )
            session.add(user)
            print(f"Created user: {email}")
        else:
            print(f"User {email} already exists.")

        await session.flush() # Get IDs

        # 3. Ensure membership exists
        result = await session.execute(
            select(UserOrg).where(UserOrg.user_id == user.id, UserOrg.org_id == org.id)
        )
        membership = result.scalar_one_or_none()
        
        if not membership:
            membership = UserOrg(
                user_id=user.id,
                org_id=org.id,
                role="administrator",
                display_name=email.split("@")[0]
            )
            session.add(membership)
            print(f"Added {email} as administrator to default organization.")
        
        await session.commit()
        print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create a local admin user.")
    parser.add_argument("--email", required=True, help="Email address for the user")
    parser.add_argument("--password", required=True, help="Password for the user")

    args = parser.parse_args()

    asyncio.run(create_user(args.email, args.password))
