# Discord Dev Portal: http://discordapp.com/developers/applications
# Requires Environment variables
#   - DISCORD_TOKEN
#   - API_URL

import discord
from discord.ext import commands, tasks
import os
import requests
import json
import tempfile
import logging
from datetime import datetime

logging.basicConfig(level=logging.DEBUG)

######################################################################
#                    Helper Functions                                #
######################################################################
file_path = None
last_command_time = datetime.now()

def load_bot_message_id():
    try:
        with open("bot_message_id.txt", "r") as f:
            return int(f.read())
    except FileNotFoundError:
        return None

def save_bot_message_id(message_id):
    with open("bot_message_id.txt", "w") as f:
        f.write(str(message_id))

bot_message_id = load_bot_message_id()

# helper function
def write_to_file(content):
    with tempfile.NamedTemporaryFile(mode='w+', delete=False) as temp:
        temp.write(content)
        temp_path = temp.name
    return temp_path

def read_and_delete_file(temp_path):
    if os.path.exists(temp_path):
        with open(temp_path, 'r') as temp:  # Open the file in text mode
            content = temp.read()
    else:
        content = None
        logging.error(f"{temp_path} doesn't exist")
    return content

def send_to_api(data):
    # API Gateway URL
    url = os.getenv('API_URL')
    if url is None:
        print("API_URL is not set in the environment variables")
        return None

    url += "/minecraft-prod/command"
    
    headers = {'Content-Type': 'application/json'}
    
    logging.info(f"Sending Data to API: {data}")
    
    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()  # Raises a HTTPError if the response status is 4xx, 5xx
    except requests.exceptions.RequestException as err:
        logging.error(f"Error occurred: {err}")
        return None

    logging.info(f"Data: {data} \nResponse: \n{response.json()}")  # To print the response from server
    
    return response

# Helper function to handle common logic in bot commands
class MinecraftCommand:
    VALID_COMMANDS = ["start", "stop", "status"]

    def __init__(self, context, command):
        self.context = context
        self.command = command
        self.bot_message = None

    async def execute(self):
        global bot_message_id
        global last_command_time
        last_command_time = datetime.now()
        if self.command not in self.VALID_COMMANDS:
            await self.on_error(f"Invalid command: {self.command}. Please use a valid command.")
            return
        try:
            if bot_message_id is not None:
                self.bot_message = await self.context.fetch_message(bot_message_id)
            else:
                self.bot_message = await self.context.send(f"User {self.context.author.name} used `{self.command}` command...")
                bot_message_id = self.bot_message.id
                save_bot_message_id(bot_message_id)

            await self.bot_message.edit(content=f"User {self.context.author.name} used `{self.command}` command...")
            data = { "command": self.command }
            response = send_to_api(data)
            logging.info(f"response: {response}")
            BOT_REPLY = response.json().get("BOT_REPLY", f"@{self.context.author}, we're sorry but we encountered a problem while processing your request. Please try again in a moment.\nIf the problem persists, don't hesitate to reach out to @The Black Mango for assistance.")
            if response is not None:
                await self.bot_message.edit(content=BOT_REPLY)
            else:
                await self.bot_message.edit(content=f"Error: Couldn't {self.command} server.")
        except Exception as e:
            logging.exception(str(e))
            await self.on_error(str(e))

    async def on_error(self, error_message):
        if self.bot_message:
            await self.bot_message.edit(content=f"Error: \n{error_message}")
        else:
            await self.context.send(f"Error: \n{error_message}")

######################################################################
#                       Discord Bot                                  #
######################################################################
# Discord bot Token
TOKEN = os.environ["DISCORD_TOKEN"]

channel_name = "mango-minecraft"
category_name = "BOT"  # Specify the category name here:

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

HELP_MESSAGES = {
    "start": " 🚀 Use this command to start the Minecraft server! Just type `!start` and watch the magic happen. ",
    "status": " 🔍 Type `!status` and I'll get the latest updates for you.",
    "stop": " 🛑 Want to pause your Minecraft journey for now? Type `!stop` and the server will safely stop, allowing you to resume later.",
}

@tasks.loop(minutes=1)  # check every minute; 
async def check_inactivity():
    global last_command_time
    inactivity_threshold = 2  # in minutes; adjust to your liking

    if (datetime.now() - last_command_time).total_seconds() // 60 > inactivity_threshold:
        if bot_message_id is not None:
            channel = bot.get_channel(id)  # replace "id" with the ID of your channel
            bot_message = await channel.fetch_message(bot_message_id)
            # Reset to initial help message
            help_message_content = ""
            for command, help_message in HELP_MESSAGES.items():
                help_message_content += f"`{command}`: {help_message}\n"
            await bot_message.edit(content=help_message_content)

# Verify that the bot is connected
@bot.event
async def on_ready():
    global bot_message_id
    print(f'{bot.user} has connected to Discord!')
    print("Servers:")

    # start the inactivity check task
    check_inactivity.start()  

    for guild in bot.guilds:
        print(f"    - {guild.name}")
        category = discord.utils.get(guild.categories, name=category_name)  # Get the category

        # If the category doesn't exist, create it 
        if category is None:
            category = await guild.create_category(category_name)

        # Fetch all channels from the guild
        all_channels = await guild.fetch_channels()

        # Filter for the category
        category_channels = [channel for channel in all_channels if channel.category == category]

        # Check if the channel already exists before creating it
        channel = discord.utils.get(category_channels, name=channel_name)
        if channel is None:
            channel = await category.create_text_channel(channel_name)

        # Clear all messages in the designated channel
        await channel.purge(limit=None)

        # Create initial help message
        help_message_content = ""
        for command, help_message in HELP_MESSAGES.items():
            help_message_content += f"`{command}`: {help_message}\n"
        bot_message = await channel.send(help_message_content)

        bot_message_id = bot_message.id
        save_bot_message_id(bot_message_id)
        
        if bot_message_id is not None:
            bot_message = await channel.fetch_message(bot_message_id)

# On Message Event
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Only process commands in the Mango-Minecraft channel
    if message.channel.name == channel_name:
        if message.content.startswith("Hello"):
            await message.channel.send("Hello!")
        await message.delete()  # delete the user's message
        await bot.process_commands(message)

# Start minecraft server
@bot.command()
async def start(context):
    """
    Starts the Minecraft server.
    """
    command = MinecraftCommand(context, "start")
    await command.execute()

# Check Server Status
@bot.command(name='status')
async def get_server_status(context):
    """
    Checks the status of the Minecraft server.
    """
    command = MinecraftCommand(context, "status")
    await command.execute()

# Stop minecraft server
@bot.command()
async def stop(context):
    """
    Stops the Minecraft server.
    """
    command = MinecraftCommand(context, "stop")
    await command.execute()

# @bot.command()
# async def help(context):
#     command = MinecraftCommand(context, "stop")
#     await command.execute()
    

# Start the discord bot
bot.run(TOKEN)

# Useful Commands
# List players
# Get average server startime / run time
# whitelist player
# kick / ban / unban a player
# backup server
# send message to all players
# get server discord usage
# display serve rlogs

