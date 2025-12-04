#!/usr/bin/env python
"""Migration script to add access_token to existing users.

This script should be run once to migrate existing users
who don't have an access_token field.
"""

import secrets

from pymongo import MongoClient


def generate_access_token() -> str:
    """Generate a secure random access token."""
    return secrets.token_urlsafe(32)


def migrate_users(mongo_uri: str = "mongodb://root:example@mongo:27017", db_name: str = "qubex") -> None:
    """Add access_token to all users without one."""
    client = MongoClient(mongo_uri)
    db = client[db_name]
    users_collection = db["user"]

    # Find users without access_token or with null access_token
    users_without_token = users_collection.find({"$or": [{"access_token": {"$exists": False}}, {"access_token": None}]})

    updated_count = 0
    for user in users_without_token:
        token = generate_access_token()
        users_collection.update_one({"_id": user["_id"]}, {"$set": {"access_token": token}})
        print(f"Updated user {user['username']} with new access token")
        updated_count += 1

    if updated_count == 0:
        print("No users needed migration")
    else:
        print(f"Successfully migrated {updated_count} users")

    client.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Migrate users to have access tokens")
    parser.add_argument("--mongo-uri", default="mongodb://root:example@mongo:27017", help="MongoDB connection URI")
    parser.add_argument("--db-name", default="qubex", help="Database name")
    args = parser.parse_args()

    migrate_users(args.mongo_uri, args.db_name)
