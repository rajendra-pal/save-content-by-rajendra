# Rajendra Save Restricted Bot
# Owner: RAJENDRA

from dotenv import load_dotenv
load_dotenv()

import os

def get_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")

# Login feature, if you want then True , if you don't want then False
LOGIN_SYSTEM = get_bool("LOGIN_SYSTEM", True) # True or False

if LOGIN_SYSTEM == False:
    # if login system is False then fill your tg account session below 
    STRING_SESSION = os.environ.get("STRING_SESSION", "").strip() or None
    if STRING_SESSION is None:
        print("STRING_SESSION is missing, so LOGIN_SYSTEM has been enabled.")
        LOGIN_SYSTEM = True
else:
    STRING_SESSION = None

# Bot token @Botfather
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# Your API ID from my.telegram.org
API_ID = int(os.environ.get("API_ID", ""))

# Your API Hash from my.telegram.org
API_HASH = os.environ.get("API_HASH", "")

# Your Owner / Admin Telegram User ID for broadcast access.
# IMPORTANT: Always set ADMINS in your environment. Default is 0 (no admin)
# so the bot refuses /broadcast unless you explicitly whitelist a user ID.
ADMINS = int(os.environ.get("ADMINS", "0"))

# Your Channel Id In Which Bot Upload Downloaded Video/File/Message etc.
# And Make Your Bot Admin In this channel with full rights.
# if you don't want to upload in channel then leave it blank don't fill anything.
CHANNEL_ID = os.environ.get("CHANNEL_ID", "")

# Your Mongodb Database Url
# Warning - Give Db uri in deploy server environment variable, don't give in repo.
DB_URI = os.environ.get("DB_URI", "") # Warning - Give Db uri in deploy server environment variable, don't give in repo.
DB_NAME = os.environ.get("DB_NAME", "RajendraBot")

# Increase time as much as possible to avoid floodwait, spamming and tg account ban issues.
WAITING_TIME = int(os.environ.get("WAITING_TIME", "10")) # time in seconds

# If You Want Error Message In Your Personal Message Then Turn It True Else If You Don't Want Then Flase
ERROR_MESSAGE = get_bool("ERROR_MESSAGE", True)
