# channels/telegram_bot.py - Telegram integration
import logging
import os  # <-- ADD THIS LINE
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

logger = logging.getLogger(__name__)

class TelegramChannel:
    """
    Telegram bot integration
    Mirrors OpenClaw's channel support but with better architecture
    """
    
    def __init__(self, connection_manager, token: str = None):
        self.manager = connection_manager
        self.token = token or os.getenv("TELEGRAM_TOKEN")
        self.application: Application = None
    
    async def start(self):
        """Start the bot"""
        if not self.token:
            logger.warning("No Telegram token provided, skipping")
            return
        
        self.application = Application.builder().token(self.token).build()
        
        # Add handlers
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("new", self.cmd_new))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
        logger.info("Starting Telegram bot...")
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
    
    async def stop(self):
        """Stop the bot"""
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        await update.message.reply_text(
            "🤖 OpenAgent Bot activated!\n\n"
            "I'm a self-hosted AI assistant running on your infrastructure.\n"
            "Commands:\n"
            "/new - Reset conversation\n"
            "/status - Show session info\n\n"
            "Just send me messages to start!"
        )
    
    async def cmd_new(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Reset session"""
        session_id = f"telegram_{update.effective_user.id}"
        if session_id in self.manager.agent_sessions:
            del self.manager.agent_sessions[session_id]
        await update.message.reply_text("✅ Session reset. Fresh start!")
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming messages"""
        session_id = f"telegram_{update.effective_user.id}"
        
        # Create session if not exists
        if session_id not in self.manager.agent_sessions:
            from agent.core import AgentRuntime
            self.manager.agent_sessions[session_id] = AgentRuntime(session_id)
        
        # Show typing indicator
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action="typing"
        )
        
        # Process through agent
        agent = self.manager.agent_sessions[session_id]
        result = await agent.process_message({
            "content": update.message.text,
            "source": "telegram",
            "user_id": update.effective_user.id
        })
        
        # Send response
        response_text = result["content"]
        
        # Add tool call info if present
        if result.get("tool_calls"):
            tool_info = result["tool_calls"]
            response_text += f"\n\n[Used tool: {tool_info.get('tool_name')}]"
        
        await update.message.reply_text(response_text)