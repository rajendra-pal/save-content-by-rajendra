# Rajendra Save Restricted Bot
# Owner: RAJENDRA

from pyrogram import Client
from config import API_ID, API_HASH, BOT_TOKEN, STRING_SESSION, LOGIN_SYSTEM

if STRING_SESSION and LOGIN_SYSTEM == False:
	RajendraUser = Client("Rajendra", api_id=API_ID, api_hash=API_HASH, session_string=STRING_SESSION)
else:
    RajendraUser = None

class Bot(Client):

    def __init__(self):
        super().__init__(
            "rajendra login",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            plugins=dict(root="Rajendra"),
            workers=150,
            sleep_threshold=5
        )


    async def start(self):

        await super().start()
        if RajendraUser is not None:
            try:
                await RajendraUser.start()
            except Exception as e:
                print(f"User client failed to start: {e}")
                globals()["RajendraUser"] = None
        print('Bot Started — Powered By RAJENDRA')

    async def stop(self, *args):

        if RajendraUser is not None:
            try:
                await RajendraUser.stop()
            except Exception:
                pass
        await super().stop()
        print('Bot Stopped Bye')

if __name__ == "__main__":
    bot = Bot()
    bot.run()

# Rajendra Save Restricted Bot
# Owner: RAJENDRA
