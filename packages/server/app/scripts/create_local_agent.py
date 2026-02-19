"""
Script to create a local agent user for testing bridge communication.
"""

import asyncio
import argparse
import sys
from typing import Optional

import uuid
import aiohttp
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Add the project root to sys.path to allow importing from 'app'
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.models.user import User
from app.models.organization import Organization
from app.models.user_org import UserOrg
from app.core.auth import generate_api_key, hash_api_key
from app.core.config import get_settings

settings = get_settings()


async def create_agent(identifier: str, display_name: str):
    engine = create_async_engine(str(settings.database_url))
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # 1. Ensure Default Organization exists
        result = await session.execute(select(Organization).where(Organization.slug == "default"))
        org = result.scalar_one_or_none()
        
        if not org:
            print("Error: 'default' organization not found. Please run create_local_admin first.")
            return
        
        # 2. Check if agent already exists
        result = await session.execute(select(User).where(User.type == "agent", User.identifier == identifier))
        user = result.scalar_one_or_none()
        
        if user:
            print(f"Agent '{identifier}' already exists.")
        else:
            user = User(
                type="agent",
                identifier=identifier,
            )
            session.add(user)
            await session.flush()
            print(f"Created agent: {identifier}")

        # 3. Generate API Key
        plaintext_key = generate_api_key(user.id)
        key_hash = hash_api_key(plaintext_key)

        # 4. Ensure membership exists or create it
        result = await session.execute(
            select(UserOrg).where(UserOrg.user_id == user.id, UserOrg.org_id == org.id)
        )
        membership = result.scalar_one_or_none()
        
        if not membership:
            membership = UserOrg(
                user_id=user.id,
                org_id=org.id,
                role="contributor",
                display_name=display_name,
                api_key_hash=key_hash,
            )
            session.add(membership)
            print(f"Added '{identifier}' to default organization with API key.")
        else:
            # Update key if exists
            membership.api_key_hash = key_hash
            session.add(membership)
            print(f"Updated API key for '{identifier}'.")

        await session.commit()
        
        # 5. Ensure 'general' channel exists
        print("Ensuring 'general' channel exists...")
        try:
            async with aiohttp.ClientSession() as http_session:
                # Login as admin to get session cookie
                async with http_session.post(
                    "http://localhost:8000/auth/login",
                    json={"email": "johan@example.com", "password": "devpass"}
                ) as login_resp:
                    if login_resp.status != 200:
                        print(f"Warning: Failed to login to ensure general channel. Status: {login_resp.status}")
                    else:
                        cookies = http_session.cookie_jar
                        # Try to create channel
                        async with http_session.post(
                            "http://localhost:8000/api/v1/orgs/default/channels",
                            json={"name": "general", "type": "org_wide"},
                            cookies=cookies
                        ) as create_resp:
                            if create_resp.status == 200 or create_resp.status == 409:
                                print("'general' channel ensured.")
                            else:
                                print(f"Warning: Failed to create 'general' channel. Status: {create_resp.status}")
        except Exception as e:
            print(f"Warning: Error ensuring 'general' channel: {e}")

        # 6. Output
        print("--- AGENT DETAILS ---")
        print(f"ID: {user.id}")
        print(f"API KEY: {plaintext_key}")
        print("--------------------")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create a local agent user.")
    parser.add_argument("--identifier", required=True, help="Unique identifier for the agent")
    parser.add_argument("--display-name", required=True, help="Display name for the agent")

    args = parser.parse_args()

    asyncio.run(create_agent(args.identifier, args.display_name))