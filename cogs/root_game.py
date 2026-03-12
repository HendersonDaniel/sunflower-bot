from discord.ext import commands
import asyncio
import time


class RootGame(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_votes = {}

    @commands.group()
    async def s(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send("Use `!s help` to see a list of command groups.")

    @s.command(name="help")
    async def s_help(self, ctx):
        await ctx.send(
            "**Sunflower Bot Commands**\n"
            "`!s help` - Show top-level command groups\n"
            "`!s root help` - Show root game commands"
        )

    @s.group()
    async def root(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send("Use `!s root help` to see a list of `root` commands.")

    @root.command(name="help")
    async def root_help(self, ctx):
        await ctx.send(
            "**Root Commands**\n"
            "`!s root play` - Start a vote between 2 random roots\n"
            "`!s root leaderboard` - Show the top 10 roots by score"
        )

    @root.command()
    async def play(self, ctx):
        """
        Makes the bot send a message of a choice of two roots to choose from.
        Similar to Karuta in that it uses emojis 1 and 2 for the choice.
        Updates the scores of the roots.
        Adds a petal to each user who votes (by giving the 1 or 2 emoji, but not both).
        """

        pair = await self.bot.root_repository.get_random_pair()
        if pair is None:
            await ctx.send("Add at least 2 roots to MongoDB before starting a vote.")
            return

        root1_data, root2_data = pair
        root1 = (
            f"1. [{root1_data['name']}] "
            f"(Root Slot: {root1_data['number']}) "
            f"Description: {root1_data['description']}"
        )
        root2 = (
            f"2. [{root2_data['name']}] "
            f"(Root Slot: {root2_data['number']}) "
            f"Description: {root2_data['description']}"
        )

        msg = await ctx.send(
                f"Which root is better? \n\n"
                f"{root1}\n"
                f"{root2}"
            )
        
        await msg.add_reaction("1️⃣")
        await msg.add_reaction("2️⃣")

        self.active_votes[msg.id] = {
            "option1": root1_data,
            "option2": root2_data,
            "votes": {},
            "channel_id": ctx.channel.id,
            "end_time": time.time() + 300
        }

        asyncio.create_task(self.close_vote(msg.id))


    async def close_vote(self, message_id):
        await asyncio.sleep(60)

        vote = self.active_votes.get(message_id)
        if vote is None:
            return

        channel = self.bot.get_channel(vote["channel_id"])
        msg = await channel.fetch_message(message_id)

        v1 = sum(1 for v in vote["votes"].values() if v == 1)
        v2 = sum(1 for v in vote["votes"].values() if v == 2)

        if v1 + v2 == 0:
            del self.active_votes[message_id]
            return

        result = await self.bot.root_repository.record_matchup(
            vote["option1"],
            vote["option2"],
            v1,
            v2,
        )
        await self.bot.root_repository.award_petals(vote["votes"].keys(), petals=1)

        del self.active_votes[message_id]

    
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):

        if payload.user_id == self.bot.user.id:
            return

        vote = self.active_votes.get(payload.message_id)
        if vote is None:
            return

        if time.time() > vote["end_time"]:
            return

        if str(payload.emoji) == "1️⃣":
            choice = 1
        elif str(payload.emoji) == "2️⃣":
            choice = 2
        else:
            return

        vote["votes"][payload.user_id] = choice

    
    @root.command()
    async def leaderboard(self, ctx):
        """
        Shows a list of top ten roots in the ranking.
        """
        roots = await self.bot.root_repository.get_leaderboard()
        if not roots:
            await ctx.send("No roots found in MongoDB.")
            return

        lines = [
            f"{index}. [{root['number']}] {root['name']} ({root['score']:.2f})"
            for index, root in enumerate(roots, start=1)
        ]
        await ctx.send("Top 10 Roots:\n" + "\n".join(lines))


async def setup(bot):
    await bot.add_cog(RootGame(bot))
