from typing import Dict

import nextcord
import nextcord.ext.commands

import logging
import os
from logging.handlers import RotatingFileHandler
import sys
import json
import yaml

from EngFroshBot import EngFroshBot

from common_models import models

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

# region Environment Variable & Deployment Type
deploy_type = os.environ.get("ENGFROSH_DEPLOY_TYPE")
development = False
production = False
if deploy_type is None:
    logger.warning("ENGFROSH_DEPLOY_TYPE environment variable not set, assuming production.")
elif deploy_type == "DEV":
    logger.info("DEVELOPMENT DEPLOYMENT VERSION")
    development = True
elif deploy_type == "PROD":
    logger.info("PRODUCTION DEPLOYMENT VERSION")
    production = True
else:
    logger.warning(f"UNKNOWN DEPLOYMENT TYPE: {deploy_type}")

# endregion

# region Load Configs
BASE_CONFIG_FILE = CURRENT_DIRECTORY + "/config/base.yaml"
DEV_CONFIG_FILE = CURRENT_DIRECTORY + "/config/dev.yaml"
PROD_CONFIG_FILE = CURRENT_DIRECTORY + "/config/prod.yaml"

with open(BASE_CONFIG_FILE) as f:
    config: Dict = yaml.load(f, Loader=yaml.SafeLoader)

if development:
    with open(DEV_CONFIG_FILE) as f:
        dev_config = yaml.load(f, Loader=yaml.SafeLoader)
        if dev_config:
            config.update(dev_config)

if production:
    with open(PROD_CONFIG_FILE) as f:
        prod_config = yaml.load(f, Loader=yaml.SafeLoader)
        if prod_config:
            config.update(prod_config)

logger.debug(f"Running with configs: {config}")

if "log_level" in config:
    stream_handler.setLevel(config["log_level"].upper())
    logger.info(f"Set stream log level to: {config['log_level'].upper()}")

# endregion

logger.debug("test")
logger.info("test")
logger.warning("test")
logger.error("test")
logger.critical("test")

# region Load Credentials
if "credentials" in config:
    with open(config["credentials"]) as f:
        credentials = json.load(f)
else:
    raise Exception("No 'credentials' file provided in config files.")

logger.info(credentials)

# endregion

# region Client Setup
client = EngFroshBot(command_prefix="!", config=config, log_channels=config["log_channels"])

# endregion

# region Load COGs
for cog in config["cogs"]:
    client.load_extension(cog)
    client.debug(f"Cog {cog} loaded")

# endregion

# region On Ready


@client.event
async def on_ready():
    """Runs on client start"""

    client.info(f"Logged on as {client.user}")
    await client.change_presence(activity=nextcord.Game(name="Hi There!", type=1, url="engfrosh.com"))

# endregion

client.run(credentials["bot_token"])
