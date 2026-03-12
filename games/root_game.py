import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!s', intents=intents)

gamekey = "root"

@bot.command(name=gamekey + 'play')
async def _root_play(ctx):
    pass




bot.add_command(_root_play)
