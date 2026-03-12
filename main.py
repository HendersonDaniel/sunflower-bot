import discord
from discord.ext import commands
import os
import asyncio
from dotenv import load_dotenv

from db import create_database

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")


async def load_cogs():
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py"):
            await bot.load_extension(f"cogs.{filename[:-3]}")


async def main():
    load_dotenv()
    mongo_client, root_repository = create_database()
    await root_repository.init_indexes()
    bot.mongo_client = mongo_client
    bot.root_repository = root_repository

    async with bot:
        await load_cogs()
        await bot.start(os.getenv("BOT_TOKEN"))


asyncio.run(main())
