@echo off
title Discord Music Bot Setup & Run
color 0A
echo ==============================
echo   Discord Music Bot Starter
echo ==============================
echo.

REM Check for Python
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo Python not found! Please install it from https://www.python.org/downloads and check "Add Python to PATH".
    pause
    exit /b
)

REM Check for FFmpeg
where ffmpeg >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo FFmpeg not found!
    echo Please download from https://ffmpeg.org/download.html and add the "bin" folder to PATH.
    pause
    exit /b
)

echo Installing dependencies...
pip install -U discord.py yt-dlp >nul

if not exist token.txt (
    echo Please paste your Discord Bot Token below:
    set /p TOKEN=Token: 
    echo %TOKEN%>token.txt
)

set /p TOKEN=<token.txt

echo Creating bot file...
(
echo import discord
echo from discord import app_commands
echo import yt_dlp
echo import asyncio
echo.
echo intents = discord.Intents.default()
echo intents.message_content = True
echo bot = discord.Client(intents=intents)
echo tree = app_commands.CommandTree(bot)
echo queue = []
echo.
echo @tree.command(name="join", description="Make the bot join your voice channel")
echo async def join(interaction: discord.Interaction):
echo.    voice = interaction.user.voice
echo.    if not voice:
echo.        await interaction.response.send_message(" You must be in a voice channel first!")
echo.        return
echo.    vc = interaction.guild.voice_client
echo.    if vc and vc.is_connected():
echo.        await interaction.response.send_message(f" Already connected to {vc.channel}")
echo.    else:
echo.        await voice.channel.connect()
echo.        await interaction.response.send_message(f" Joined {voice.channel}!")
echo.
echo @tree.command(name="play", description="Play a song or playlist from YouTube")
echo async def play(interaction: discord.Interaction, query: str):
echo.    await interaction.response.defer()
echo.    voice = interaction.user.voice
echo.    if not voice:
echo.        await interaction.followup.send(" You must be in a voice channel.")
echo.        return
echo.    vc = interaction.guild.voice_client or await voice.channel.connect()
echo.    with yt_dlp.YoutubeDL({'format': 'bestaudio'}) as ydl:
echo.        info = ydl.extract_info(query, download=False)
echo.        if 'entries' in info:
echo.            for e in info['entries']:
echo.                queue.append(e['url'])
echo.            await interaction.followup.send(f" Added playlist **{info.get('title', 'playlist')}**")
echo.        else:
echo.            queue.append(info['url'])
echo.            await interaction.followup.send(f" Added **{info['title']}**")
echo.    if not vc.is_playing():
echo.        await play_next(interaction, vc)
echo.
echo async def play_next(interaction, vc):
echo.    if not queue:
echo.        await vc.disconnect()
echo.        return
echo.    url = queue.pop(0)
echo.    with yt_dlp.YoutubeDL({'format': 'bestaudio'}) as ydl:
echo.        info = ydl.extract_info(url, download=False)
echo.        audio_url = info['url']
echo.    source = await discord.FFmpegOpusAudio.from_probe(audio_url, method='fallback')
echo.    vc.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(interaction, vc), bot.loop))
echo.    await interaction.followup.send(f" Now playing: **{info['title']}**")
echo.
echo @tree.command(name="skip", description="Skip the current song")
echo async def skip(interaction: discord.Interaction):
echo.    vc = interaction.guild.voice_client
echo.    if vc and vc.is_playing():
echo.        vc.stop()
echo.        await interaction.response.send_message(" Skipped!")
echo.    else:
echo.        await interaction.response.send_message(" Nothing is playing.")
echo.
echo @tree.command(name="stop", description="Stop music and leave")
echo async def stop(interaction: discord.Interaction):
echo.    vc = interaction.guild.voice_client
echo.    if vc:
echo.        queue.clear()
echo.        await vc.disconnect()
echo.        await interaction.response.send_message(" Stopped and disconnected.")
echo.    else:
echo.        await interaction.response.send_message(" Not connected.")
echo.
echo @bot.event
echo async def on_ready():
echo.    await tree.sync()
echo.    print(f" Logged in as {bot.user}")
echo.
echo bot.run(open("token.txt").read().strip())
) > musicbot.py

cls
echo  Setup complete! Starting your bot...
echo.
python musicbot.py
pause
