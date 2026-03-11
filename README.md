# ChizuruAI — Local Discord Bot powered by Qwen3.5-27B

A fully local Discord bot that runs **Qwen3.5-27B** on your machine via **Ollama** and interacts with users in your server.

## Prerequisites

- **Python 3.10+**
- **NVIDIA GPU** with CUDA 
- **Ollama** — https://ollama.com
- A **Discord Bot Token**

## 1. Create a Discord Bot

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click **New Application** → name it (e.g. "Chizuru")
3. Go to **Bot** tab → click **Reset Token** → **copy the token**
4. Under **Privileged Gateway Intents**, enable:
   - **Message Content Intent**
5. Go to **OAuth2 → URL Generator**:
   - Scopes: `bot`
   - Bot Permissions: `Send Messages`, `Read Message History`, `Read Messages/View Channels`
6. Copy the generated URL, open it in your browser, and invite the bot to your server

## 2. Install Ollama

Download and install from https://ollama.com

Then pull the model:
```bash
ollama pull qwen3.5:27b
```

## 3. Install uv & Bot Dependencies

```bash
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
cd ChizuruAI
uv sync
```

## 4. Configure

Edit the `.env` file and set your Discord bot token:

```
DISCORD_TOKEN=paste_your_token_here
```

You can also customize the system prompt, temperature, max tokens, etc. in `.env`.

## 5. Run

**Make sure Ollama is running** (it starts automatically after install, or run `ollama serve`).

### Start the Discord bot
```bash
start_bot.bat
```
Or manually:
```bash
uv run bot.py
```

## Usage

| Action | How |
|---|---|
| Talk to the bot | **@Chizuru** your message |
| DM the bot | Send a direct message |
| Clear history | `!clear` |
| Check status | `!status` |
| Change personality | `!setprompt <new prompt>` (bot owner only) |

## Architecture

```
Discord ←→ bot.py (discord.py) ←→ Ollama OpenAI API (localhost:11434) ←→ Qwen3.5-27B (GPU)
```

- **bot.py** uses the OpenAI Python client to talk to Ollama's OpenAI-compatible endpoint
- Per-channel conversation history is kept in memory
- The bot only responds when **@mentioned** or **DM'd**

## Troubleshooting

| Issue | Fix |
|---|---|
| Bot says "Ollama unreachable" | Make sure Ollama is running (`ollama serve` or check system tray) |
| Out of VRAM | Try a smaller quant: `ollama pull qwen3.5:27b-q4_K_M` |
| Slow first response | First request loads the model into VRAM — subsequent responses are fast |
| Bot doesn't respond | Make sure you **@mention** it, and Message Content Intent is enabled |
