# Add this code to the TOP of your musicbot.py file

from flask import Flask
from threading import Thread

# Simple health check server for Fly.io
app = Flask('')

@app.route('/')
def home():
    return "Discord Bot is running!"

@app.route('/health')
def health():
    return "OK", 200

def run_web_server():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_web_server)
    t.daemon = True
    t.start()

# Start the health check server
keep_alive()

# YOUR EXISTING BOT CODE STARTS BELOW THIS LINE
import os
import asyncio
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import traceback

import discord
from discord import app_commands
from discord.ext import commands, tasks
import yt_dlp
from dotenv import load_dotenv

# Load .env
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN not set in environment. Create a .env with DISCORD_TOKEN=your_token")

# Enhanced Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('music_bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger("music-bot")

# Intents
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True
intents.members = True

# Bot with better configuration
class MusicBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
            chunk_guilds_at_startup=False
        )
        self.cleanup_loop_started = False

    async def setup_hook(self):
        """Called when the bot is starting up"""
        # Start the cleanup loop only after the bot is ready
        if not self.cleanup_loop_started:
            self.cleanup_loop.start()
            self.cleanup_loop_started = True
        await self.tree.sync()
        logger.info("Application commands synced")

    @tasks.loop(minutes=5)
    async def cleanup_loop(self):
        """Clean up unused guild states and disconnected voice clients"""
        try:
            guilds_to_remove = []
            
            for guild_id, state in list(guild_states.items()):
                guild = self.get_guild(guild_id)
                if not guild:
                    guilds_to_remove.append(guild_id)
                    continue
                    
                vc = guild.voice_client
                if (not vc or not vc.is_connected()) and not state.queue and not state.current:
                    guilds_to_remove.append(guild_id)
            
            for guild_id in guilds_to_remove:
                guild_states.pop(guild_id, None)
                state_message_channel_map.pop(guild_id, None)
                
            if guilds_to_remove:
                logger.info(f"Cleaned up {len(guilds_to_remove)} unused guild states")
                
        except Exception as e:
            logger.error(f"Error in cleanup loop: {e}")

    @cleanup_loop.before_loop
    async def before_cleanup(self):
        await self.wait_until_ready()

bot = MusicBot()
tree = bot.tree

# ----- Enhanced yt_dlp Configuration -----
YTDL_OPTS = {
    'format': 'bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
    'noplaylist': True,
    'ignoreerrors': True,
    'logtostderr': False,
    'extract_flat': False,
    'audioformat': 'mp3',
    'restrictfilenames': True,
    'nocheckcertificate': True,
}

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -probesize 32 -analyzeduration 32",
    "options": "-vn -bufsize 1024k -af volume=0.5",
}

# Rate limiting
class RateLimiter:
    def __init__(self, max_requests: int = 10, window: int = 60):
        self.max_requests = max_requests
        self.window = window
        self.requests = {}

    def is_rate_limited(self, user_id: int) -> bool:
        now = asyncio.get_event_loop().time()
        if user_id not in self.requests:
            self.requests[user_id] = []
        
        # Remove old requests
        self.requests[user_id] = [req_time for req_time in self.requests[user_id] if now - req_time < self.window]
        
        if len(self.requests[user_id]) >= self.max_requests:
            return True
            
        self.requests[user_id].append(now)
        return False

rate_limiter = RateLimiter()

# ----- Enhanced Data Classes -----
@dataclass
class Song:
    title: str
    webpage_url: str
    duration: Optional[int] = None
    requester: Optional[discord.Member] = None
    stream_url: Optional[str] = None
    thumbnail: Optional[str] = None

    def duration_str(self) -> str:
        if not self.duration:
            return "Unknown"
        mins = int(self.duration // 60)
        secs = int(self.duration % 60)
        if mins >= 60:
            hours = mins // 60
            mins = mins % 60
            return f"{hours}:{mins:02d}:{secs:02d}"
        return f"{mins}:{secs:02d}"

@dataclass
class GuildMusic:
    guild_id: int
    queue: List[Song] = field(default_factory=list)
    history: List[Song] = field(default_factory=list)
    current: Optional[Song] = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    volume: float = 0.5
    loop: bool = False
    skip_votes: set = field(default_factory=set)

guild_states: Dict[int, GuildMusic] = {}
state_message_channel_map: Dict[int, int] = {}

def get_guild_state(guild_id: int) -> GuildMusic:
    if guild_id not in guild_states:
        guild_states[guild_id] = GuildMusic(guild_id=guild_id)
    return guild_states[guild_id]

# ----- Enhanced YTDLSource -----
class YTDLSource:
    @staticmethod
    async def create_source(search: str, requester: discord.Member, loop: asyncio.AbstractEventLoop = None) -> List[Song]:
        loop = loop or asyncio.get_event_loop()
        
        # Rate limiting check
        if rate_limiter.is_rate_limited(requester.id):
            raise Exception("You're making too many requests. Please wait a moment.")
        
        ytdl_instance = yt_dlp.YoutubeDL(YTDL_OPTS)
        
        try:
            data = await loop.run_in_executor(
                None, 
                lambda: ytdl_instance.extract_info(search, download=False)
            )
        except Exception as e:
            logger.error(f"Failed to extract info for '{search}': {e}")
            raise Exception(f"Failed to search for '{search}': {str(e)}")

        if not data:
            raise Exception("No data returned from YouTube")

        songs: List[Song] = []
        try:
            if 'entries' in data:
                entries = [e for e in data['entries'] if e]
                if not entries:
                    raise Exception("No videos found in search results")
                    
                for entry in entries:
                    if not entry:
                        continue
                    songs.append(Song(
                        title=entry.get('title', 'Unknown Title'),
                        webpage_url=entry.get('webpage_url', entry.get('url', '')),
                        duration=int(entry.get('duration', 0)) if entry.get('duration') else None,
                        requester=requester,
                        thumbnail=entry.get('thumbnail'),
                        stream_url=None
                    ))
            else:
                songs.append(Song(
                    title=data.get('title', 'Unknown Title'),
                    webpage_url=data.get('webpage_url', ''),
                    duration=int(data.get('duration', 0)) if data.get('duration') else None,
                    requester=requester,
                    thumbnail=data.get('thumbnail'),
                    stream_url=None
                ))
        except Exception as e:
            logger.error(f"Error processing YouTube data: {e}")
            raise Exception("Error processing video data")

        if not songs:
            raise Exception("No playable videos found")

        return songs

    @staticmethod
    async def resolve_stream_url(song: Song, loop: asyncio.AbstractEventLoop = None):
        if song.stream_url:
            return song.stream_url
            
        loop = loop or asyncio.get_event_loop()
        ytdl_instance = yt_dlp.YoutubeDL(YTDL_OPTS)
        
        try:
            data = await loop.run_in_executor(
                None, 
                lambda: ytdl_instance.extract_info(song.webpage_url, download=False)
            )
            if not data or 'url' not in data:
                raise Exception("No stream URL found")
                
            song.stream_url = data['url']
            return song.stream_url
            
        except Exception as e:
            logger.error(f"Failed to resolve stream URL for {song.title}: {e}")
            raise Exception(f"Failed to get audio stream: {str(e)}")

# ----- Enhanced Music Controls View -----
class MusicControls(discord.ui.View):
    def __init__(self, guild_id: int, ctx_channel_id: int):
        super().__init__(timeout=300)  # 5 minute timeout
        self.guild_id = guild_id
        self.ctx_channel_id = ctx_channel_id
        self.message: Optional[discord.Message] = None

    async def on_timeout(self):
        """Disable all buttons on timeout"""
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass

    async def _get_voice_client(self, interaction: discord.Interaction) -> Optional[discord.VoiceClient]:
        if not interaction.guild:
            return None
        return interaction.guild.voice_client

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check if user is in the same voice channel"""
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("You need to be in a voice channel to use these controls.", ephemeral=True)
            return False
            
        vc = await self._get_voice_client(interaction)
        if not vc or not vc.channel:
            await interaction.response.send_message("I'm not currently in a voice channel.", ephemeral=True)
            return False
            
        if interaction.user.voice.channel.id != vc.channel.id:
            await interaction.response.send_message("You need to be in the same voice channel as me to use these controls.", ephemeral=True)
            return False
            
        return True

    @discord.ui.button(label="⏯ Play/Pause", style=discord.ButtonStyle.primary)
    async def play_pause(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = await self._get_voice_client(interaction)
        if not vc:
            await interaction.response.send_message("Not connected to voice.", ephemeral=True)
            return
            
        if vc.is_paused():
            vc.resume()
            await interaction.response.send_message("▶️ Resumed playback", ephemeral=True)
        elif vc.is_playing():
            vc.pause()
            await interaction.response.send_message("⏸️ Paused playback", ephemeral=True)
        else:
            await interaction.response.send_message("Nothing is currently playing.", ephemeral=True)

    @discord.ui.button(label="⏭ Skip", style=discord.ButtonStyle.secondary)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = await self._get_voice_client(interaction)
        state = get_guild_state(self.guild_id)
        
        if not vc or not vc.is_connected():
            await interaction.response.send_message("Not connected to voice.", ephemeral=True)
            return
            
        if not vc.is_playing():
            await interaction.response.send_message("Nothing is currently playing.", ephemeral=True)
            return
            
        # Vote skipping
        required_votes = max(1, len(vc.channel.members) // 2)
        state.skip_votes.add(interaction.user.id)
        
        if len(state.skip_votes) >= required_votes or interaction.user.guild_permissions.administrator:
            state.skip_votes.clear()
            vc.stop()
            await interaction.response.send_message("⏭️ Skipped song", ephemeral=True)
        else:
            await interaction.response.send_message(
                f"Voted to skip ({len(state.skip_votes)}/{required_votes} votes needed)",
                ephemeral=True
            )

    @discord.ui.button(label="⏹ Stop", style=discord.ButtonStyle.danger)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = await self._get_voice_client(interaction)
        state = get_guild_state(self.guild_id)
        
        if vc and vc.is_connected():
            state.queue.clear()
            state.history.clear()
            state.current = None
            state.skip_votes.clear()
            vc.stop()
            await vc.disconnect()
            await interaction.response.send_message("⏹️ Stopped playback and disconnected", ephemeral=True)
        else:
            await interaction.response.send_message("Not connected to voice.", ephemeral=True)

    @discord.ui.button(label="🔊 Vol+", style=discord.ButtonStyle.primary)
    async def vol_up(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = get_guild_state(self.guild_id)
        state.volume = min(state.volume + 0.1, 2.0)
        
        vc = await self._get_voice_client(interaction)
        if vc and vc.source and hasattr(vc.source, 'volume'):
            vc.source.volume = state.volume
            
        await interaction.response.send_message(f"🔊 Volume: {int(state.volume * 100)}%", ephemeral=True)

    @discord.ui.button(label="🔉 Vol-", style=discord.ButtonStyle.primary)
    async def vol_down(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = get_guild_state(self.guild_id)
        state.volume = max(state.volume - 0.1, 0.0)
        
        vc = await self._get_voice_client(interaction)
        if vc and vc.source and hasattr(vc.source, 'volume'):
            vc.source.volume = state.volume
            
        await interaction.response.send_message(f"🔉 Volume: {int(state.volume * 100)}%", ephemeral=True)

# ----- Enhanced Playback Helpers -----
async def ensure_voice(ctx_or_interaction) -> Optional[discord.VoiceClient]:
    """Ensure the bot is in the user's voice channel"""
    if isinstance(ctx_or_interaction, commands.Context):
        author = ctx_or_interaction.author
        guild = ctx_or_interaction.guild
    else:
        author = ctx_or_interaction.user
        guild = ctx_or_interaction.guild

    if not author or not author.voice or not author.voice.channel:
        return None
        
    channel = author.voice.channel
    
    # Check permissions
    if not channel.permissions_for(guild.me).connect:
        raise Exception(f"I don't have permission to join {channel.mention}")
    if not channel.permissions_for(guild.me).speak:
        raise Exception(f"I don't have permission to speak in {channel.mention}")
    
    vc = guild.voice_client
    
    if vc and vc.is_connected():
        if vc.channel.id != channel.id:
            await vc.move_to(channel)
        return vc
    else:
        return await channel.connect(timeout=60.0, reconnect=True)

def _play_next_after(guild: discord.Guild, error: Optional[Exception] = None):
    """Callback for when a song finishes playing"""
    if error:
        logger.error(f"Playback error in guild {guild.id}: {error}")
    
    coro = _play_next(guild)
    fut = asyncio.run_coroutine_threadsafe(coro, bot.loop)
    try:
        fut.result(timeout=30)  # 30 second timeout
    except Exception as e:
        logger.error(f"Error in after play callback for guild {guild.id}: {e}")

async def _play_next(guild: discord.Guild):
    """Play the next song in the queue"""
    state = get_guild_state(guild.id)
    
    async with state.lock:
        # Clear skip votes when moving to next song
        state.skip_votes.clear()
        
        if state.loop and state.current:
            # Re-add current song to queue if loop is enabled
            state.queue.insert(0, state.current)
        
        if not state.queue:
            state.current = None
            # Disconnect after 1 minute of inactivity
            await asyncio.sleep(60)
            vc = guild.voice_client
            if vc and not vc.is_playing() and not state.queue:
                await vc.disconnect()
            return
            
        next_song = state.queue.pop(0)
        state.current = next_song
        state.history.append(next_song)
        
        # Keep history manageable
        if len(state.history) > 50:
            state.history = state.history[-50:]
        
        vc = guild.voice_client
        if not vc or not vc.is_connected():
            return
            
        try:
            # Resolve stream URL if needed
            if not next_song.stream_url:
                await YTDLSource.resolve_stream_url(next_song)
                
            # Create audio source with error handling
            source = discord.FFmpegPCMAudio(
                next_song.stream_url, 
                **FFMPEG_OPTIONS
            )
            volume_adjusted = discord.PCMVolumeTransformer(source, volume=state.volume)
            
            vc.play(volume_adjusted, after=lambda e: _play_next_after(guild, e))
            
            # Send now playing message
            await send_now_playing(guild, next_song)
            
        except Exception as e:
            logger.error(f"Error playing {next_song.title} in guild {guild.id}: {e}")
            # Try next song
            await _play_next(guild)

async def send_now_playing(guild: discord.Guild, song: Song):
    """Send now playing message to the appropriate text channel"""
    text_channel_id = state_message_channel_map.get(guild.id)
    if not text_channel_id:
        return
        
    text_channel = guild.get_channel(text_channel_id)
    if not text_channel:
        # Try to find an alternative channel
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                text_channel = channel
                state_message_channel_map[guild.id] = channel.id
                break
    
    if text_channel:
        embed = discord.Embed(
            title="🎵 Now Playing",
            description=f"**{song.title}**",
            color=discord.Color.blue()
        )
        embed.add_field(name="Duration", value=song.duration_str(), inline=True)
        if song.requester:
            embed.add_field(name="Requested by", value=song.requester.mention, inline=True)
        
        if song.thumbnail:
            embed.set_thumbnail(url=song.thumbnail)
            
        embed.set_footer(text=f"Volume: {int(get_guild_state(guild.id).volume * 100)}%")
        
        try:
            view = MusicControls(guild.id, text_channel.id)
            message = await text_channel.send(embed=embed, view=view)
            view.message = message
        except Exception as e:
            logger.error(f"Failed to send now playing message in guild {guild.id}: {e}")

# ----- Enhanced Commands -----
@tree.command(name="join", description="Make the bot join your voice channel")
async def slash_join(interaction: discord.Interaction):
    """Join the user's voice channel"""
    await interaction.response.defer(thinking=True)
    
    try:
        vc = await ensure_voice(interaction)
        if vc:
            state_message_channel_map[interaction.guild.id] = interaction.channel.id
            await interaction.followup.send(f"✅ Joined {vc.channel.mention}")
        else:
            await interaction.followup.send("❌ You need to be in a voice channel for me to join.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)

@tree.command(name="leave", description="Disconnect the bot from voice")
async def slash_leave(interaction: discord.Interaction):
    """Leave the voice channel"""
    await interaction.response.defer(thinking=True)
    
    vc = interaction.guild.voice_client
    if vc and vc.is_connected():
        state = get_guild_state(interaction.guild.id)
        state.queue.clear()
        state.current = None
        state.skip_votes.clear()
        await vc.disconnect()
        guild_states.pop(interaction.guild.id, None)
        state_message_channel_map.pop(interaction.guild.id, None)
        await interaction.followup.send("✅ Disconnected from voice channel")
    else:
        await interaction.followup.send("❌ I'm not connected to a voice channel.", ephemeral=True)

@tree.command(name="play", description="Play a song or add to queue")
@app_commands.describe(query="YouTube search or URL")
async def slash_play(interaction: discord.Interaction, query: str):
    """Play music from YouTube"""
    if not query or len(query) > 200:
        await interaction.response.send_message("❌ Please provide a valid search query or URL (max 200 characters).", ephemeral=True)
        return
        
    await interaction.response.defer(thinking=True)
    
    try:
        vc = await ensure_voice(interaction)
        if not vc:
            await interaction.followup.send("❌ You need to be in a voice channel for me to join.", ephemeral=True)
            return

        songs = await YTDLSource.create_source(query, interaction.user)
        if not songs:
            await interaction.followup.send("❌ No songs found for your search.", ephemeral=True)
            return

        state = get_guild_state(interaction.guild.id)
        state.queue.extend(songs)
        state_message_channel_map[interaction.guild.id] = interaction.channel.id

        if not vc.is_playing() and not vc.is_paused():
            await _play_next(interaction.guild)

        if len(songs) == 1:
            await interaction.followup.send(f"✅ Added **{songs[0].title}** to the queue")
        else:
            await interaction.followup.send(f"✅ Added {len(songs)} songs to the queue")
            
    except Exception as e:
        logger.error(f"Play command error: {e}")
        await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)

@tree.command(name="queue", description="Show the current queue")
async def slash_queue(interaction: discord.Interaction):
    """Display the current queue"""
    await interaction.response.defer(thinking=True)
    
    state = get_guild_state(interaction.guild.id)
    
    if not state.queue and not state.current:
        await interaction.followup.send("🎵 The queue is empty")
        return

    embed = discord.Embed(title="🎵 Music Queue", color=discord.Color.green())
    
    if state.current:
        embed.add_field(
            name="Now Playing",
            value=f"**{state.current.title}**\n{state.current.duration_str()} | {state.current.requester.mention if state.current.requester else 'Unknown'}",
            inline=False
        )

    if state.queue:
        queue_text = ""
        for idx, song in enumerate(state.queue[:10], 1):
            queue_text += f"`{idx}.` **{song.title}** ({song.duration_str()}) | {song.requester.mention if song.requester else 'Unknown'}\n"
        
        if len(state.queue) > 10:
            queue_text += f"\n... and {len(state.queue) - 10} more songs"
            
        embed.add_field(name="Up Next", value=queue_text, inline=False)
    else:
        embed.add_field(name="Up Next", value="No songs in queue", inline=False)

    embed.set_footer(text=f"Total songs in queue: {len(state.queue)}")
    await interaction.followup.send(embed=embed)

@tree.command(name="skip", description="Skip the current song")
async def slash_skip(interaction: discord.Interaction):
    """Skip the current song"""
    await interaction.response.defer(thinking=True)
    
    vc = interaction.guild.voice_client
    state = get_guild_state(interaction.guild.id)
    
    if not vc or not vc.is_connected():
        await interaction.followup.send("❌ I'm not connected to a voice channel.", ephemeral=True)
        return
        
    if not vc.is_playing():
        await interaction.followup.send("❌ Nothing is currently playing.", ephemeral=True)
        return

    vc.stop()
    await interaction.followup.send("✅ Skipped current song")

@tree.command(name="pause", description="Pause the current song")
async def slash_pause(interaction: discord.Interaction):
    """Pause playback"""
    vc = interaction.guild.voice_client
    
    if not vc or not vc.is_connected():
        await interaction.response.send_message("❌ I'm not connected to a voice channel.", ephemeral=True)
        return
        
    if vc.is_paused():
        await interaction.response.send_message("❌ Playback is already paused.", ephemeral=True)
    elif vc.is_playing():
        vc.pause()
        await interaction.response.send_message("⏸️ Paused playback")
    else:
        await interaction.response.send_message("❌ Nothing is currently playing.", ephemeral=True)

@tree.command(name="resume", description="Resume playback")
async def slash_resume(interaction: discord.Interaction):
    """Resume playback"""
    vc = interaction.guild.voice_client
    
    if not vc or not vc.is_connected():
        await interaction.response.send_message("❌ I'm not connected to a voice channel.", ephemeral=True)
        return
        
    if vc.is_paused():
        vc.resume()
        await interaction.response.send_message("▶️ Resumed playback")
    elif vc.is_playing():
        await interaction.response.send_message("❌ Playback is not paused.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Nothing is currently playing.", ephemeral=True)

@tree.command(name="volume", description="Set the volume (0-200%)")
@app_commands.describe(level="Volume level (0-200)")
async def slash_volume(interaction: discord.Interaction, level: int):
    """Set playback volume"""
    if level < 0 or level > 200:
        await interaction.response.send_message("❌ Volume must be between 0 and 200.", ephemeral=True)
        return
        
    state = get_guild_state(interaction.guild.id)
    state.volume = level / 100.0
    
    vc = interaction.guild.voice_client
    if vc and vc.source and hasattr(vc.source, 'volume'):
        vc.source.volume = state.volume
        
    await interaction.response.send_message(f"🔊 Volume set to {level}%")

@tree.command(name="clear", description="Clear the queue")
async def slash_clear(interaction: discord.Interaction):
    """Clear the music queue"""
    state = get_guild_state(interaction.guild.id)
    queue_size = len(state.queue)
    state.queue.clear()
    state.skip_votes.clear()
    
    await interaction.response.send_message(f"✅ Cleared {queue_size} songs from the queue")

# Enhanced error handling
@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    """Handle voice state updates for auto-disconnect"""
    if member.id == bot.user.id:
        return
        
    guild = member.guild
    vc = guild.voice_client
    
    if vc and vc.is_connected():
        # Check if bot is alone in voice channel
        if len(vc.channel.members) == 1 and vc.channel.members[0].id == bot.user.id:
            state = get_guild_state(guild.id)
            state.queue.clear()
            state.current = None
            await vc.disconnect()
            logger.info(f"Auto-disconnected from {guild.name} due to being alone")

@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    """Handle command errors"""
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"❌ Command on cooldown. Try again in {error.retry_after:.1f}s")
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.send(f"❌ I'm missing permissions: {', '.join(error.missing_permissions)}")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send(f"❌ You're missing permissions: {', '.join(error.missing_permissions)}")
    else:
        logger.error(f"Command error in {ctx.guild.name}: {error}")
        await ctx.send("❌ An error occurred while executing that command.")

@bot.event
async def on_ready():
    """Bot is ready"""
    logger.info(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    logger.info(f"✅ Connected to {len(bot.guilds)} guilds")
    
    # Set bot status
    activity = discord.Activity(type=discord.ActivityType.listening, name="/play")
    await bot.change_presence(activity=activity)

# Run the bot
if __name__ == "__main__":
    try:
        bot.run(TOKEN)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.critical(f"Bot crashed: {e}")
        raise