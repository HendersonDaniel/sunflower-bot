import math
import os
import random
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReturnDocument


def utc_now():
    return datetime.now(timezone.utc)


class RootRepository:
    def __init__(self, database):
        self.database = database
        self.roots = database["roots"]
        self.users = database["users"]

    async def init_indexes(self):
        await self.roots.create_index("number")
        await self.roots.create_index("name", unique=True)
        await self.roots.create_index("score")
        await self.users.create_index("discord_user_id", unique=True)
        await self.users.create_index("petals")

    async def create_root(self, name, number, description, score=0.0):
        now = utc_now()
        document = {
            "name": name,
            "number": int(number),
            "description": description,
            "score": float(score),
            "wins": 0,
            "losses": 0,
            "ties": 0,
            "comparisons": 0,
            "created_at": now,
            "updated_at": now,
        }
        await self.roots.insert_one(document)
        return document

    async def get_random_pair(self):
        roots = await self.roots.find().to_list(length=None)
        if len(roots) < 2:
            return None

        if len(roots) == 2:
            return roots

        anchor = min(
            random.sample(roots, k=min(5, len(roots))),
            key=lambda root: (root.get("comparisons", 0), random.random()),
        )

        other_roots = [root for root in roots if root["_id"] != anchor["_id"]]
        if not other_roots:
            return None

        if random.random() < 0.2:
            opponent = random.choice(other_roots)
            return [anchor, opponent]

        anchor_score = float(anchor.get("score", 0.0))
        opponent = min(
            random.sample(other_roots, k=min(10, len(other_roots))),
            key=lambda root: (
                abs(float(root.get("score", 0.0)) - anchor_score),
                root.get("comparisons", 0),
                random.random(),
            ),
        )
        return [anchor, opponent]

    async def get_leaderboard(self, limit=10, root_number=None):
        query = {}
        if root_number is not None:
            query["number"] = int(root_number)

        cursor = self.roots.find(query).sort("score", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def award_petals(self, discord_user_ids, petals=1):
        now = utc_now()
        totals = {}
        for discord_user_id in discord_user_ids:
            result = await self.users.find_one_and_update(
                {"discord_user_id": discord_user_id},
                {
                    "$inc": {"petals": petals},
                    "$set": {"updated_at": now},
                    "$setOnInsert": {
                        "discord_user_id": discord_user_id,
                        "created_at": now,
                    },
                },
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
            totals[discord_user_id] = result["petals"]
        return totals

    async def get_user_petals(self, discord_user_id):
        return await self.users.find_one({"discord_user_id": discord_user_id})

    async def get_petal_leaderboard(self, limit=10):
        cursor = self.users.find().sort("petals", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def record_matchup(self, root1, root2, votes1, votes2):
        total_votes = votes1 + votes2
        if total_votes <= 0:
            return None

        current1 = float(root1.get("score", 0.0))
        current2 = float(root2.get("score", 0.0))
        expected1 = 1 / (1 + math.exp(current2 - current1))
        actual1 = votes1 / total_votes
        delta = 24 * (actual1 - expected1)

        next1 = current1 + delta
        next2 = current2 - delta
        now = utc_now()

        if votes1 > votes2:
            update1 = {"wins": 1, "comparisons": 1}
            update2 = {"losses": 1, "comparisons": 1}
        elif votes2 > votes1:
            update1 = {"losses": 1, "comparisons": 1}
            update2 = {"wins": 1, "comparisons": 1}
        else:
            update1 = {"ties": 1, "comparisons": 1}
            update2 = {"ties": 1, "comparisons": 1}

        await self.roots.update_one(
            {"_id": root1["_id"]},
            {
                "$set": {"score": next1, "updated_at": now},
                "$inc": update1,
            },
        )
        await self.roots.update_one(
            {"_id": root2["_id"]},
            {
                "$set": {"score": next2, "updated_at": now},
                "$inc": update2,
            },
        )


def create_database():
    mongo_uri = os.getenv("MONGODB_URI")
    database_name = os.getenv("MONGODB_DB_NAME", "sunflower-db")

    if not mongo_uri:
        raise RuntimeError("Missing MONGODB_URI in environment.")

    client = AsyncIOMotorClient(mongo_uri)
    database = client[database_name]
    return client, RootRepository(database)
