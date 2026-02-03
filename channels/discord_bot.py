import logging
import os
import asyncio
from typing import Optional

logger = logging.getLogger(__name__)

class DiscordChannel:
    """Discord bot integration for AgentVault"""
    
    def __init__(self, connection_manager, token: Optional[str] = None):
        self.manager = connection_manager
        self.token = token or os.getenv("DISCORD_TOKEN")
    
    async def start(self):
        if not self.token:
            logger.warning("No Discord token provided, skipping")
            return
        
        try:
            import discord
            from discord.ext import commands
            
            intents = discord.Intents.default()
            intents.message_content = True
            bot = commands.Bot(command_prefix="!", intents=intents)
            
            @bot.event
            async def on_ready():
                logger.info(f"Discord bot logged in as {bot.user}")
            
            @bot.event
            async def on_message(message):
                if message.author == bot.user:
                    return
                
                if bot.user.mentioned_in(message) or isinstance(message.channel, discord.DMChannel):
                    from agent.core import AgentRuntime
                    session_id = f"discord_{message.author.id}"
                    
                    if session_id not in self.manager.agent_sessions:
                        self.manager.agent_sessions[session_id] = AgentRuntime(session_id)
                    
                    agent = self.manager.agent_sessions[session_id]
                    
                    async with message.channel.typing():
                        result = await agent.process_message({
                            "content": message.content.replace(f"<@{bot.user.id}>", "").strip(),
                            "user_id": str(message.author.id)
                        })
                    
                    await message.reply(result["content"][:2000])
            
            await bot.start(self.token)
            
        except ImportError:
            logger.error("discord.py not installed. Run: pip install discord.py")
        except Exception as e:
            logger.error(f"Discord error: {e}")
    
    async def stop(self):
        pass