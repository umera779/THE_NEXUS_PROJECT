#!/usr/bin/env python3
"""
scripts/create_admin.py
─────────────────────────
Standalone script to create admin or super_admin users directly in the database.
Run this SEPARATELY from the main app (not through the API) for initial setup.

Usage:
    python scripts/create_admin.py

Requirements:
    - .env file configured with DATABASE_URL
    - Database tables must already exist (run the app once in dev mode to auto-create them)
"""
import asyncio
import sys
import os

# Make sure we can import from app/
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.models import User, UserRole
from sqlalchemy.future import select


async def create_admin_user():
    print("=== Legacy Portal— Admin User Creation ===\n")

    first_name = input("First Name: ").strip()
    last_name = input("Last Name: ").strip()
    email = input("Email: ").strip().lower()
    phone = input("Phone Number: ").strip()
    password = input("Password: ").strip()

    print("\nRole options:")
    print("  1. admin")
    print("  2. super_admin")
    role_choice = input("Select role (1 or 2): ").strip()
    role = "super_admin" if role_choice == "2" else "admin"

    confirm = input(f"\nCreate {role} account for {email}? (yes/no): ").strip().lower()
    if confirm != "yes":
        print("Cancelled.")
        return

    async with AsyncSessionLocal() as db:
        # Check duplicate
        result = await db.execute(select(User).where(User.email == email))
        existing = result.scalar_one_or_none()
        if existing:
            print(f"ERROR: Email {email} is already registered.")
            return

        user = User(
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone_number=phone,
            password_hash=hash_password(password),
            role=role,
            is_email_verified=True,
            account_status="active",
        )
        db.add(user)
        await db.commit()
        print(f"\n✓ {role} account created for {email} (ID: {user.id})")


if __name__ == "__main__":
    asyncio.run(create_admin_user())
