import discord
from discord.ext import commands
import asyncio
# Using yt-dlp, the maintained successor to youtube-dl
import yt_dlp as youtube_dl 
from dotenv import load_dotenv
import os

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# --- Configuration ---
# Suppress noise about console usage from youtube_dl
youtube_dl.utils.bug_reports_message = lambda: ''

# Configuration for yt-dlp to extract the best audio format
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'noplaylist': True,
    'quiet': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0', # Allows IPv4 for better streaming compatibility
}

# FFmpeg options for streaming audio
# The reconnect options help if the stream buffers or briefly drops
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

# --- Bot Setup ---
# Bot intents: required for message content and voice state (must be enabled in Developer Portal)
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True 

bot = commands.Bot(command_prefix='!', intents=intents)

# --- YTDL Source Class (Handles YouTube Audio Extraction) ---
class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        
        # We need to run the extraction in an executor to prevent blocking the bot's main thread
        with youtube_dl.YoutubeDL(YDL_OPTIONS) as ydl:
            # We use a partial function to pass the URL and settings to the executor
            partial = lambda: ydl.extract_info(url, download=not stream)
            info = await loop.run_in_executor(None, partial)
        
        if 'entries' in info:
            # Take the first item from a playlist/search result
            info = info['entries'][0]

        # Get the final streaming URL from the info dictionary
        stream_url = info['url']
        
        # Create the FFmpeg audio source
        return cls(discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTIONS), data=info)

# --- Bot Events and Commands ---

@bot.event
async def on_ready():
    print(f'Bot connected as {bot.user}')

@bot.command(name='play', help='To play a song from a YouTube URL')
async def play(ctx, *, url):
    # 1. Check if user is in a voice channel
    if not ctx.message.author.voice:
        await ctx.send(f"{ctx.message.author.name} is not connected to a voice channel.")
        return

    channel = ctx.message.author.voice.channel 
    voice_client = ctx.voice_client

    # 2. Handle bot connection/movement
    if voice_client is None:
        # Bot is not in a voice channel, connect now
        voice_client = await channel.connect()
    elif voice_client.channel != channel:
        # Bot is in a different channel, move it
        await voice_client.move_to(channel)

    try:
        # Stop any currently playing audio before starting a new one
        if voice_client.is_playing():
            voice_client.stop()
            
        await ctx.send(f'Processing audio for: {url}')
        
        # Get the audio source asynchronously and stream it
        player = await YTDLSource.from_url(url, loop=bot.loop, stream=True)
        
        # FIX FOR: "unexpected keyword argument 'before'" error
        def after_playing(error):
            if error:
                print(f'Player error on completion: {error}')
            # Optional: Add logic here to disconnect or play next song in a queue

        # Start playback
        voice_client.play(player, after=after_playing)
        await ctx.send(f'Now playing: **{player.title}**')

    except Exception as e:
        print(f"An error occurred: {e}")
        await ctx.send(f"An error occurred while trying to play the video: {e}")


@bot.command(name='leave', help='To make the bot leave the voice channel')
async def leave(ctx):
    if ctx.voice_client is not None:
        # Stop playback and disconnect
        if ctx.voice_client.is_playing():
             ctx.voice_client.stop()
        await ctx.voice_client.disconnect()
        await ctx.send('Disconnected from the voice channel.')
    else:
        await ctx.send('I am not connected to a voice channel.')

# --- Run the Bot ---
bot.run(TOKEN)