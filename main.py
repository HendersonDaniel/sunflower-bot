import discord
from discord.ext import commands
import os
import asyncio
import logging
from dotenv import load_dotenv

from db import create_database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("sunflower-bot")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


async def sf_help_command(ctx):
    logger.info("`!sf help` requested")
    await ctx.send(
        "**Sunflower Bot Commands**\n"
        "`!sf help` - Show top-level command groups\n"
        "`!sf leaderboard` - Show the top 10 petal leaderboard\n"
        "`!sf slap` - Slap Sunflower to make it drop petals\n"
        "`!sf root help` - Show root game commands"
    )


@bot.event
async def on_ready():
    logger.info("Logged in as %s (ID: %s)", bot.user, bot.user.id)

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    logger.info(
        "Message received guild=%s channel=%s",
        getattr(message.guild, "id", "DM"),
        message.channel.id,
    )
    await bot.process_commands(message)


@bot.event
async def on_command(ctx):
    logger.info(
        "Command invoked name=%s channel=%s",
        ctx.command.qualified_name,
        ctx.channel.id,
    )


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        logger.warning("Unknown command received in channel %s", ctx.channel.id)
        return

    logger.exception("Command error for command=%s", getattr(ctx.command, "qualified_name", "unknown"), exc_info=error)
    if isinstance(getattr(error, "original", error), discord.Forbidden):
        logger.error("Cannot send error message in channel %s due to missing permissions", ctx.channel.id)
        return

    try:
        await ctx.send(f"Command error: `{error}`")
    except discord.Forbidden:
        logger.error("Cannot send error message in channel %s due to missing permissions", ctx.channel.id)


async def load_cogs():
    for filename in sorted(os.listdir("./cogs")):
        if filename.endswith(".py"):
            logger.info("Loading cog %s", filename)
            await bot.load_extension(f"cogs.{filename[:-3]}")

    sf_group = bot.get_command("sf")
    if sf_group is None:
        raise RuntimeError("The `sf` command group was not loaded.")

    if sf_group.get_command("help") is None:
        sf_group.add_command(commands.Command(sf_help_command, name="help"))


async def main():
    load_dotenv()
    logger.info("Starting bot")
    mongo_client, root_repository = create_database()
    await root_repository.init_indexes()
    bot.mongo_client = mongo_client
    bot.root_repository = root_repository

    async with bot:
        await load_cogs()
        await bot.start(os.getenv("BOT_TOKEN"))


asyncio.run(main())
