from discord.ext import commands
import discord
import asyncio
import logging

logger = logging.getLogger("sunflower-bot.root-game")
VOTE_TIMEOUT_SECONDS = 60


def format_root_option(index, root):
    return (
        f"{index}. [{root['name']}] "
        f"(Root Slot: {root['number']})\n"
        f"{root['description']}"
    )


def format_user_mention(user=None, user_id=None):
    if user is not None:
        return user.mention
    if user_id is not None:
        return f"<@{user_id}>"
    return ""


def build_root_game_message(root1, root2, ping_user=None):
    prompt_prefix = f"{format_user_mention(user=ping_user)} " if ping_user is not None else ""
    return f"{prompt_prefix}Which root is better?\n\n{root1}\n\n{root2}"


def build_petal_message(voter_id, total_petals):
    user_mention = format_user_mention(user_id=voter_id)
    return (
        f"Thank you for playing the root game {user_mention}. \n"
        f"You earned 1 Petal. \nTotal Petals: {total_petals}"
    )


class RootGame(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_votes = {}

    @commands.group()
    async def sf(self, ctx):
        if ctx.invoked_subcommand is None:
            logger.info("Top-level help requested by %s", ctx.author.id)
            await ctx.send("Use `!sf help` to see a list of command groups.")

    @sf.group()
    async def root(self, ctx):
        if ctx.invoked_subcommand is None:
            logger.info("Root help requested by %s", ctx.author.id)
            await ctx.send("Use `!sf root help` to see a list of `root` commands.")

    @root.command(name="help")
    async def root_help(self, ctx):
        logger.info("`!sf root help` requested by %s", ctx.author.id)
        await ctx.send(
            "**Root Commands**\n"
            "`!sf root play` - Play the root game\n"
            "`!sf root leaderboard [root_number]` - Show the top 10 roots leaderboard, optionally filtered by root slot"
        )

    @root.command()
    async def play(self, ctx):
        await self.start_root_game(
            channel=ctx.channel,
            reply_target=ctx.message,
            mention_author=True,
            ping_user=None,
        )

    async def start_root_game(self, channel, reply_target=None, mention_author=False, ping_user=None):
        logger.info("Starting root game for channel=%s", channel.id)
        pair = await self.bot.root_repository.get_random_pair()
        if pair is None:
            logger.warning("Root game start failed: fewer than 2 roots in database")
            await channel.send("Add at least 2 roots to the database before playing the root game.")
            return

        root1_data, root2_data = pair
        root1 = format_root_option(1, root1_data)
        root2 = format_root_option(2, root2_data)

        message_text = build_root_game_message(root1, root2, ping_user=ping_user)
        if reply_target is not None:
            msg = await reply_target.reply(
                message_text,
                mention_author=mention_author,
            )
        else:
            msg = await channel.send(message_text)

        await msg.add_reaction("1️⃣")
        await msg.add_reaction("2️⃣")

        self.active_votes[msg.id] = {
            "option1": root1_data,
            "option2": root2_data,
            "message": msg,
            "seen_voters": set(),
            "vote_count": 0,
        }
        logger.info("Vote created message_id=%s", msg.id)
        asyncio.create_task(self.expire_vote(msg.id, timeout_seconds=VOTE_TIMEOUT_SECONDS))

    def build_play_again_view(self):
        return PlayAgainView(self)

    async def process_vote(self, message_id, winning_choice, voter_id):
        vote = self.active_votes.get(message_id)
        if vote is None:
            logger.info("Vote %s already cleared before processing vote", message_id)
            return

        logger.info(
            "Processing vote %s winner=%s voter=%s",
            message_id,
            winning_choice,
            voter_id,
        )
        votes1 = 1 if winning_choice == 1 else 0
        votes2 = 1 if winning_choice == 2 else 0

        result = await self.bot.root_repository.record_matchup(
            vote["option1"],
            vote["option2"],
            votes1,
            votes2,
        )
        if result is None:
            logger.info("Vote %s had no tally to record", message_id)
            await vote["message"].reply(
                "Root game expired with no response.",
                view=self.build_play_again_view(),
            )
            return

        total_petals = await self.bot.root_repository.award_petals([voter_id], petals=1)
        total_petals = total_petals.get(voter_id, 0)
        vote["vote_count"] += 1
        logger.info("Awarded 1 petal to user %s for vote %s", voter_id, message_id)

        await vote["message"].reply(
            build_petal_message(voter_id, total_petals),
            view=self.build_play_again_view(),
        )

    async def expire_vote(self, message_id, timeout_seconds=60):
        await asyncio.sleep(timeout_seconds)

        if message_id not in self.active_votes:
            logger.info("Vote %s already resolved before timeout", message_id)
            return

        vote = self.active_votes.pop(message_id, None)
        if vote is None:
            logger.info("Vote %s already resolved during timeout cleanup", message_id)
            return

        if vote["vote_count"] == 0:
            logger.info("Vote %s expired with no responses", message_id)
            await vote["message"].reply(
                "Root game expired with no response.",
                view=self.build_play_again_view(),
            )
            return

        logger.info("Vote %s closed after %s unique votes", message_id, vote["vote_count"])

    
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        logger.info(
            "Reaction add message_id=%s user_id=%s emoji=%s",
            payload.message_id,
            payload.user_id,
            payload.emoji,
        )

        if payload.user_id == self.bot.user.id:
            return

        vote = self.active_votes.get(payload.message_id)
        if vote is None:
            return

        if str(payload.emoji) == "1️⃣":
            choice = 1
        elif str(payload.emoji) == "2️⃣":
            choice = 2
        else:
            return

        if payload.user_id in vote["seen_voters"]:
            logger.info(
                "Ignoring duplicate vote message_id=%s user_id=%s choice=%s",
                payload.message_id,
                payload.user_id,
                choice,
            )
            return

        vote["seen_voters"].add(payload.user_id)

        logger.info(
            "Recorded vote message_id=%s user_id=%s choice=%s",
            payload.message_id,
            payload.user_id,
            choice,
        )
        await self.process_vote(payload.message_id, choice, payload.user_id)

    
    @root.command()
    async def leaderboard(self, ctx, root_number: int | None = None):
        """
        Shows a list of top ten roots in the ranking.
        """
        logger.info("Leaderboard requested by %s filter=%s", ctx.author.id, root_number)
        roots = await self.bot.root_repository.get_leaderboard(root_number=root_number)
        if not roots:
            if root_number is None:
                await ctx.send("No roots found in MongoDB.")
            else:
                await ctx.send(f"No roots found for root slot {root_number}.")
            return

        lines = [
            f"{index}. ({root['number']}) [{root['name']}] ({root['score']:.2f})"
            for index, root in enumerate(roots, start=1)
        ]
        header = "Top 10 Roots:" if root_number is None else f"Top 10 Roots for Slot {root_number}:"
        await ctx.send(header + "\n" + "\n".join(lines))

    @sf.command(name="leaderboard")
    async def petals_leaderboard(self, ctx):
        logger.info("Petal leaderboard requested by %s", ctx.author.id)
        users = await self.bot.root_repository.get_petal_leaderboard()
        if not users:
            await ctx.send("No petal data found.")
            return

        lines = []
        for index, user in enumerate(users, start=1):
            display_name = await self.get_user_display_name(ctx, user["discord_user_id"])
            lines.append(f"{index}. {display_name} ({user['petals']} petals)")

        await ctx.send("Top 10 Petals:\n" + "\n".join(lines))

    async def get_user_display_name(self, ctx, discord_user_id):
        if ctx.guild:
            member = ctx.guild.get_member(discord_user_id)
            if member:
                return member.display_name

        user = self.bot.get_user(discord_user_id)
        if user:
            return user.name

        try:
            user = await self.bot.fetch_user(discord_user_id)
        except Exception:
            return f"User {discord_user_id}"

        return user.name


async def setup(bot):
    await bot.add_cog(RootGame(bot))


class PlayAgainView(discord.ui.View):
    def __init__(self, root_game_cog):
        super().__init__(timeout=None)
        self.root_game_cog = root_game_cog

    @discord.ui.button(label="Play Again", style=discord.ButtonStyle.primary)
    async def play_again(self, interaction, button):
        logger.info("Play again requested by user=%s channel=%s", interaction.user.id, interaction.channel.id)
        await interaction.response.defer()
        await self.root_game_cog.start_root_game(
            channel=interaction.channel,
            reply_target=interaction.message,
            mention_author=True,
            ping_user=interaction.user,
        )
