import os
import re
import asyncio
import logging
from collections import defaultdict, deque

import httpx
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
MODEL_NAME = os.getenv("MODEL_NAME", "qwen3.5:27b")
SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    "You are Chizuru, a helpful and friendly AI assistant.",
)
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "1024"))
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.7"))
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "20"))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("chizuru")

# ---------------------------------------------------------------------------
# HTTP client for Ollama native API
# ---------------------------------------------------------------------------
http_client = httpx.AsyncClient(base_url=OLLAMA_BASE_URL, timeout=300.0)

# ---------------------------------------------------------------------------
# Conversation memory  –  per-channel history
# ---------------------------------------------------------------------------
# Each channel keeps a deque of {"role": ..., "content": ...} dicts.
channel_histories: dict[int, deque] = defaultdict(
    lambda: deque(maxlen=MAX_HISTORY * 2)  # *2 because each exchange = user+assistant
)

# ---------------------------------------------------------------------------
# Discord bot setup
# ---------------------------------------------------------------------------
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


def _build_messages(channel_id: int, user_message: str) -> list[dict]:
    """Build the full messages list: system + history + new user message."""
    # /no_think disables Qwen3.5's thinking mode for direct responses
    messages = [{"role": "system", "content": SYSTEM_PROMPT + "\n/no_think"}]
    messages.extend(channel_histories[channel_id])
    messages.append({"role": "user", "content": user_message})
    return messages


async def _generate(channel_id: int, user_message: str) -> str:
    """Call the local Ollama server and return the assistant reply."""
    messages = _build_messages(channel_id, user_message)

    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "stream": False,
        "think": False,
        "options": {
            "num_predict": MAX_TOKENS,
            "temperature": TEMPERATURE,
        },
    }

    resp = await http_client.post("/api/chat", json=payload)
    resp.raise_for_status()
    data = resp.json()

    raw = data.get("message", {}).get("content", "")
    log.info(f"[DEBUG] Raw model output ({len(raw)} chars):\n{raw[:2000]}")
    # Safety net: strip any <think> tags if they still appear
    reply = re.sub(r"<think>[\s\S]*?</think>", "", raw).strip()
    log.info(f"[DEBUG] After stripping think tags ({len(reply)} chars):\n{reply[:500]}")

    if not reply:
        reply = "Hmm, I thought about it but couldn't come up with a response. Try asking again!"

    # Store the exchange in history
    channel_histories[channel_id].append({"role": "user", "content": user_message})
    channel_histories[channel_id].append({"role": "assistant", "content": reply})

    return reply


# ---------------------------------------------------------------------------
# Split long messages for Discord's 2 000-char limit
# ---------------------------------------------------------------------------
def _split_response(text: str, limit: int = 1990) -> list[str]:
    """Split text into chunks that fit within Discord's message limit."""
    if len(text) <= limit:
        return [text]

    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        # Try to split at a newline
        split_at = text.rfind("\n", 0, limit)
        if split_at == -1:
            # Fall back to splitting at a space
            split_at = text.rfind(" ", 0, limit)
        if split_at == -1:
            split_at = limit
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------
@bot.event
async def on_ready():
    log.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    log.info(f"Model: {MODEL_NAME}")
    log.info(f"Ollama endpoint: {OLLAMA_BASE_URL}")
    log.info("Bot is ready!")


@bot.event
async def on_message(message: discord.Message):
    # Ignore own messages
    if message.author == bot.user:
        return

    # Process commands first (like !clear)
    await bot.process_commands(message)

    # Only respond when mentioned or in DMs
    is_dm = isinstance(message.channel, discord.DMChannel)
    is_mentioned = bot.user in message.mentions

    if not is_dm and not is_mentioned:
        return

    # Don't re-process commands
    ctx = await bot.get_context(message)
    if ctx.valid:
        return

    # Strip the bot mention from the message text
    user_text = message.content
    if is_mentioned:
        user_text = user_text.replace(f"<@{bot.user.id}>", "").strip()
        user_text = user_text.replace(f"<@!{bot.user.id}>", "").strip()

    if not user_text:
        await message.reply("Hey! What's on your mind?")
        return

    # Show typing indicator while generating
    async with message.channel.typing():
        try:
            reply = await _generate(message.channel.id, user_text)
        except Exception as e:
            log.error(f"Generation error: {e}", exc_info=True)
            await message.reply(
                "Sorry, I couldn't generate a response. "
                "Make sure Ollama is running!"
            )
            return

    # Send the response (split if needed)
    chunks = _split_response(reply)
    for i, chunk in enumerate(chunks):
        if i == 0:
            await message.reply(chunk)
        else:
            await message.channel.send(chunk)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
@bot.command(name="clear")
async def clear_history(ctx: commands.Context):
    """Clear conversation history for this channel."""
    channel_histories[ctx.channel.id].clear()
    await ctx.reply("Conversation history cleared!")


@bot.command(name="status")
async def status(ctx: commands.Context):
    """Check bot and model status."""
    try:
        resp = await http_client.get("/api/tags")
        resp.raise_for_status()
        models = [m["name"] for m in resp.json().get("models", [])]
        await ctx.reply(
            f"**Status:** Online\n"
            f"**Model:** {MODEL_NAME}\n"
            f"**Available models:** {', '.join(models)}\n"
            f"**History length (this channel):** "
            f"{len(channel_histories[ctx.channel.id])} messages"
        )
    except Exception as e:
        await ctx.reply(f"**Status:** Online, but Ollama unreachable.\n`{e}`")


@bot.command(name="setprompt")
@commands.is_owner()
async def set_prompt(ctx: commands.Context, *, prompt: str):
    """(Owner only) Change the system prompt at runtime."""
    global SYSTEM_PROMPT
    SYSTEM_PROMPT = prompt
    # Clear all histories since they were based on the old prompt
    channel_histories.clear()
    await ctx.reply(f"System prompt updated and histories cleared.")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
def main():
    if not DISCORD_TOKEN or DISCORD_TOKEN == "your_discord_bot_token_here":
        log.error(
            "DISCORD_TOKEN not set! Edit .env and add your bot token.\n"
            "Get one at https://discord.com/developers/applications"
        )
        return
    bot.run(DISCORD_TOKEN)


if __name__ == "__main__":
    main()
