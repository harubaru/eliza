import json

import discord
from discord.commands import SlashCommandGroup, Option
from discord.ext import commands

import logging
from core.logging import get_logger
from core.utils import get_guild, get_roles

logger = get_logger(__name__)

class AuthCog(commands.Cog, name='Auth', description='Used by server admins to authorize the bot.'):
    def __init__(self, bot):
        self.bot = bot
        self.auth_file = 'auth.json'

        try:
            open(self.auth_file, 'r')
        except FileNotFoundError:
            logger.info(f'Auth file not found. Writing a new one to {self.auth_file}...')
            with open(self.auth_file, 'w') as fp:
                fp.write(json.dumps({"0":{}}))
    
    def supporter_auth(self, ctx: discord.ApplicationContext):
        if get_guild() is not None:
            member = get_guild().get_member(ctx.author.id)
            if member is None:
                return False
            else:
                if get_roles() is None:
                    return False
                for role in get_roles():
                    if member.get_role(role.id) is not None:
                        return True
        else:
            return False

    
    @commands.slash_command(name='toggle', description='Toggle this AI chatbot in a specific channel.')
    @discord.default_permissions(
        administrator=True,
    )
    async def toggle(self, ctx: discord.ApplicationContext, channel: discord.TextChannel):
        try:
            if ctx.guild.member_count < 40 and not self.supporter_auth(ctx):
                await ctx.send_response(content='Unable to authorize for guilds with less than 40 members. You can get around this by supporting us on Patreon or boosting our server!', ephemeral=True)
                return
            with open(self.auth_file, 'r') as fp:
                auth_data = json.load(fp)
            with open(self.auth_file, 'w') as fp:
                channel_id = str(channel.id)
                if channel_id not in auth_data:
                    logger.info(f'Authorizing channel ID {channel_id}')
                    auth_data[channel_id] = {}
                    fp.write(json.dumps(auth_data))
                    await ctx.send_response(content='Enabled this channel for this AI to use.', ephemeral=True)
                else:
                    logger.info(f'Deauthorizing channel ID {channel_id}')
                    del auth_data[channel_id]
                    fp.write(json.dumps(auth_data))
                    await ctx.send_response(content='Disabled this channel for this AI to use.', ephemeral=True)
        except Exception as e:
            embed = discord.Embed(title='Toggle failed.', description=f'An exception has occurred while toggling the AI.\nError: {e}')
            await ctx.send_response(embed=embed, ephemeral=True)

def setup(bot):
    bot.add_cog(AuthCog(bot))
