import logging
import random
from datetime import datetime, timezone

from discord.ext import commands


logger = logging.getLogger("sunflower-bot.slap-game")
SLAP_COOLDOWN_SECONDS = 30 * 60
SLAP_RESPONSES = [
    "Ahn!",
    "How DARE you!?",
    "FUCK!",
    "*Falls dramatically to the ground and wiggles vigorously*",
]


def roll_slap_petals():
    petals = 1
    while random.random() > 0.1:
        petals += 1
    return petals


def build_success_message(display_name, petals):
    response = random.choice(SLAP_RESPONSES)
    petal_word = "petal" if petals == 1 else "petals"
    return f"{response}\n\n{display_name} slapped Sunflower and caused it to drop {petals} {petal_word}."


def format_remaining_cooldown(cooldown_until):
    if cooldown_until is None:
        return "less than a minute"

    if cooldown_until.tzinfo is None:
        cooldown_until = cooldown_until.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    remaining_seconds = max(0, int((cooldown_until - now).total_seconds()))
    if remaining_seconds < 60:
        return "less than a minute"

    minutes, seconds = divmod(remaining_seconds, 60)
    hours, minutes = divmod(minutes, 60)

    parts = []
    if hours:
        hour_word = "hour" if hours == 1 else "hours"
        parts.append(f"{hours} {hour_word}")
    if minutes:
        minute_word = "minute" if minutes == 1 else "minutes"
        parts.append(f"{minutes} {minute_word}")
    return " ".join(parts) if parts else "less than a minute"


def build_blocked_message(cooldown_until):
    remaining = format_remaining_cooldown(cooldown_until)
    return f"Sunflower BLOCKED your slap. It is still on guard. Perhaps try again in {remaining}."


class SlapGame(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def slap(self, ctx):
        logger.info("`!sf slap` requested by user=%s", ctx.author.id)
        petals = roll_slap_petals()
        slap_result = await self.bot.root_repository.attempt_slap(
            petals=petals,
            cooldown_seconds=SLAP_COOLDOWN_SECONDS,
        )

        if not slap_result["success"]:
            slap_state = slap_result["state"] or {}
            cooldown_until = slap_state.get("cooldown_until")
            await ctx.send(build_blocked_message(cooldown_until))
            return

        totals = await self.bot.root_repository.award_petals([ctx.author.id], petals=petals)
        total_petals = totals.get(ctx.author.id, petals)
        await ctx.send(
            build_success_message(ctx.author.display_name, petals)
            + f"\nTotal Petals: {total_petals}"
        )


async def setup(bot):
    cog = SlapGame(bot)
    await bot.add_cog(cog)

    sf_group = bot.get_command("sf")
    if sf_group is None:
        raise RuntimeError("The `sf` command group must be loaded before slap commands.")

    slap_command = next((command for command in cog.get_commands() if command.name == "slap"), None)
    if slap_command is None:
        raise RuntimeError("The slap command was not registered on the cog.")
    if sf_group.get_command("slap") is None:
        sf_group.add_command(slap_command)
