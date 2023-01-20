from typing import Dict

import nextcord
from nextcord import Intents
import nextcord.ext.commands

import logging
import os
from logging.handlers import RotatingFileHandler
import sys
import yaml

from EngFroshBot import EngFroshBot


def recursive_update(config: dict, type_config: dict) -> dict:
    for key, value in type_config.items():
        if isinstance(value, dict) and config.get(key, None) is not None:
            config[key] = recursive_update(config[key], value)
        else:
            config[key] = value
    return config


CURRENT_DIRECTORY = os.path.dirname(__file__)
DEFAULT_LOG_LEVEL = logging.DEBUG

# region Logging Setup
SCRIPT_NAME = os.path.splitext(os.path.basename(__file__))[0]

logger = logging.getLogger(SCRIPT_NAME)

file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

LOG_DIRECTORY = CURRENT_DIRECTORY + "/logs/"

if not os.path.exists(LOG_DIRECTORY):
    os.mkdir(LOG_DIRECTORY)

DEBUG_LOG_FILE = LOG_DIRECTORY + "/{}_debug.log".format(SCRIPT_NAME)
INFO_LOG_FILE = LOG_DIRECTORY + "/{}_info.log".format(SCRIPT_NAME)
WARNING_LOG_FILE = LOG_DIRECTORY + "/{}_warning.log".format(SCRIPT_NAME)
ERROR_LOG_FILE = LOG_DIRECTORY + "/{}_error.log".format(SCRIPT_NAME)

debug_handler = RotatingFileHandler(DEBUG_LOG_FILE, maxBytes=19 * 1024 * 1024, backupCount=20)
debug_handler.setLevel("DEBUG")
debug_handler.setFormatter(file_formatter)

info_handler = RotatingFileHandler(INFO_LOG_FILE, maxBytes=19 * 1024 * 1024, backupCount=10)
info_handler.setLevel("INFO")
info_handler.setFormatter(file_formatter)

warning_handler = RotatingFileHandler(WARNING_LOG_FILE, maxBytes=19 * 1024 * 1024, backupCount=10)
warning_handler.setLevel("WARNING")
warning_handler.setFormatter(file_formatter)

error_handler = RotatingFileHandler(ERROR_LOG_FILE, maxBytes=19 * 1024 * 1024, backupCount=10)
error_handler.setLevel("ERROR")
error_handler.setFormatter(file_formatter)

logging.getLogger().setLevel("DEBUG")
logging.getLogger().addHandler(debug_handler)
logging.getLogger().addHandler(info_handler)
logging.getLogger().addHandler(warning_handler)
logging.getLogger().addHandler(error_handler)

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setLevel(DEFAULT_LOG_LEVEL)
stream_handler.setFormatter(file_formatter)
logging.getLogger().addHandler(stream_handler)

# endregion

# region Environment Variable, Deployment Type, and Bot Token
deploy_type = os.environ.get("ENGFROSH_DEPLOY_TYPE")
config_type = os.environ.get("ENGFROSH_CONFIG_TYPE")
if config_type is None:
    logger.error("No config specified!")
    exit()
development = False
production = True
if deploy_type is None:
    logger.warning("ENGFROSH_DEPLOY_TYPE environment variable not set, assuming production.")
elif deploy_type == "DEV":
    logger.info("DEVELOPMENT DEPLOYMENT VERSION")
    development = True
    production = False
elif deploy_type == "PROD":
    logger.info("PRODUCTION DEPLOYMENT VERSION")
    production = True
else:
    logger.error("UNKNOWN DEPLOYMENT VERSION")

bot_token = os.environ.get("DISCORD_BOT_TOKEN")

# endregion

# region Load Configs
BASE_CONFIG_FILE = CURRENT_DIRECTORY + "/config/base.yaml"
CONFIG_FILE = CURRENT_DIRECTORY + "/config/" + config_type + ".yaml"

with open(BASE_CONFIG_FILE) as f:
    config: Dict = yaml.load(f, Loader=yaml.SafeLoader)

with open(CONFIG_FILE) as f:
    new_config = yaml.load(f, Loader=yaml.SafeLoader)
    if new_config:
        config = recursive_update(config, new_config)
logger.debug(f"Running with configs: {config}")

if "log_level" in config:
    stream_handler.setLevel(config["log_level"].upper())
    logger.info(f"Set stream log level to: {config['log_level'].upper()}")

# endregion


intents = Intents.default()
intents.message_content = True
intents.messages = True
intents.members = True

# region Client Setup
client = EngFroshBot(config=config, log_channel=config["bot_log_channel"], intents=intents)

EngFroshBot.instance = client

# endregion

# region Load COGs
for cog in config["modules"]["cogs"]:
    client.load_extension(cog)
    client.info(f"Cog {cog} loaded", send_to_discord=False)

# endregion

# region On Ready


@client.event
async def on_ready():
    """Runs on client start"""

    client.info(f"Logged on as {client.user}")
    await client.change_presence(activity=nextcord.Game(name="Welcome to EngFrosh!", type=1, url="mars.engfrosh.com"))

# endregion
client.run(bot_token)
