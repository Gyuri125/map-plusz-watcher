# Biztonság

## Titkok

Ez a repó nyilvános. **Soha ne** nyiss olyan issue-t, pull requestet vagy
commitot, amely tartalmazza a következőket:

- Discord webhook URL,
- Telegram bot token,
- SMTP jelszó,
- bármilyen más API-kulcs vagy jelszó.

A helyi titkokat a `.env` fájlba tedd (a `.gitignore` kizárja), GitHub
Actions alatt pedig repository secretként add meg.

Ha egy titok véletlenül kikerül:

1. a Discordban töröld a webhookot, és készíts újat;
2. a Telegramon a @BotFather `/revoke` parancsával új tokent kérj;
3. frissítsd a GitHub secretet és a helyi `.env`-et;
4. ha a titok commitba került, a git historyból is tisztítsd ki.

## Sebezhetőség jelentése

Ha biztonsági hibát találsz, ne nyilvános issue-ban jelezd. Használd a
GitHub **Security > Report a vulnerability** funkcióját, vagy vedd fel a
kapcsolatot a repó tulajdonosával.
