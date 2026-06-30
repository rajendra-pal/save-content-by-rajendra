<h1 align="center">
  Rajendra Save Restricted Bot
</h1>


*A Telegram Bot, Which Can Send You Restricted Content By Its Post Link With <b>Login Feature.</b>*

*Added **TG Account Protection** Security To Prevent Account From Ban Issue, Not Totally But Now TG Account Ban Chance Is Low.*

---

## Variables

- `LOGIN_SYSTEM` : Set True or False As per your need.
- `STRING_SESSION` : Your Tg Account Session String, if login is False then this variable is compulsory to fill. ( ⚠️ Warning - Give string session on deploy website environment variable, don't give in repo )
- `API_HASH` : Your API Hash From [Telegram Website](https://my.telegram.org)
- `API_ID` : Your API ID From [Telegram Website](https://my.telegram.org)
- `BOT_TOKEN` : Your Bot Token From [BotFather](https://telegram.me/BotFather) ( ⚠️ Warning - Give Bot Token on deploy website environment variable, don't give in repo )
- `ADMINS` : **Your** Telegram User ID (numeric) for admin access like `/broadcast`. **Always set this in your environment** — leaving it unset disables `/broadcast` entirely. Get your ID from [@userinfobot](https://t.me/userinfobot) on Telegram.
- `CHANNEL_ID` : Your Channel Id On Which Bot Upload Downloaded Content. ( And Make Your Bot Admin In This Channel With Full Rights )
- `DB_URI` : Your Mongodb Database Url From [Mongodb](https://mongodb.com) ( ⚠️ Warning - Give Db Url on deploy website environment variable, don't give in repo )
- `WAITING_TIME` : Increase Time To Avoid Spamming, Floodwait and Tg Account Ban Issue.
- `ERROR_MESSAGE` : Set True Or False, If You Want Error Message Then True Else False.

---

## Commands

- `/start` : Check Bot Is Working Or Not
- `/help` : Check How To Use Bot
- `/login` : Login Your Telegram String Session
- `/logout` : Logout Your Session
- `/cancel` : Cancel Your Any Ongoing Task
- `/broadcast` : Broadcast Message To User (Admin Only)

### Customization Commands

- `/setthumb` : Reply to a photo to set it as your custom thumbnail.
- `/viewthumb` : View your current custom thumbnail.
- `/delthumb` : Remove your custom thumbnail.
- `/settitle <text>` : Set a title prefix prepended to every upload.
- `/viewtitle` : View your current custom title.
- `/deltitle` : Remove your custom title.
- `/replace oldword|newword` : Add a find/replace rule.
- `/removeword <word>` : Strip a word from every caption/text.
- `/viewrules` : Show all your find/replace rules and removed words.
- `/clearrules` : Clear all find/replace rules and removed words.

---

## Usage

__FOR PUBLIC CHATS__

_just send post/s link_


__FOR PRIVATE CHATS__

_first send invite link of the chat (unnecessary if the account of string session already member of the chat)
then send post/s link_


__FOR BOT CHATS__

_send link with '/b/', bot's username and message id, you might want to install some unofficial client (like - Plus Messenger) to get the id like below_


```
https://t.me/b/botusername/4321
```

__BATCH POSTS__

_send the starting post link, then type how many posts you want to save._


```
https://t.me/xxxx/1001 10

https://t.me/c/xxxx/101 20
```

_This saves from the starting post onward. Old ranges like `1001-1010` still work._

---

## Credits

- Maintained by **RAJENDRA**.
