# Setting up the Discord side

About 3 minutes. You need a Discord account and that's it.

## 1. Make the application

1. Go to https://discord.com/developers/applications and hit **New Application**.
2. Name it whatever you want. It doesn't have to be Carzty. Accept the terms, create.
3. Optional but nice: give it an avatar on the **General Information** page.

## 2. Get the token

1. Left sidebar → **Bot**.
2. Hit **Reset Token**, confirm, and copy it.
3. Keep it handy. The installer's setup wizard asks for it (and checks it with Discord for you).

> The token is basically the bot's password. Don't commit it, don't paste it in Discord, don't put it
> in a screenshot. If it leaks, hit Reset Token again and the old one dies immediately.

While you're on the Bot page:

- **Privileged Gateway Intents:** leave all three **off**. Carzty doesn't read messages or member lists.
- **Public Bot:** turn it **off** if you only want *you* to be able to invite it. Leave it on if you're
  running it for friends.

## 3. Set up installation

Left sidebar → **Installation**.

1. **Installation Contexts:** tick both **User Install** and **Guild Install**.
   - Guild Install = invite it to a server like a normal bot.
   - User Install = add it to your account and use `/task` anywhere, even servers it isn't in
     (reminders go to your DMs in that case).
2. **Install Link:** pick **Discord Provided Link**.
3. **Default Install Settings:**
   - **User Install** scopes: `applications.commands`
   - **Guild Install** scopes: `applications.commands` and `bot`
   - **Guild Install** permissions: `View Channels`, `Send Messages`, `Send Messages in Threads`, `Embed Links`
4. Save.

## 4. Invite it

The setup wizard prints both invite links when it finishes (and the bot logs the server one every time it
starts). You can also copy the install link from the Installation page. They look like:

```
https://discord.com/oauth2/authorize?client_id=<your app id>&scope=bot+applications.commands&permissions=274877926400
```

Open the link, pick **Add to server** (or **Add to my apps** for the user install), done.

## 5. Make sure DMs can actually reach you

By default reminders go to your DMs. If Discord blocks DMs from server members for the server the
bot is in, the reminders bounce. Fix: right click the server → **Privacy Settings** → turn on
**Direct Messages**. Or use `deliver:Post in this channel` on your tasks.

## 6. Lock it down (optional)

The wizard offers to lock the bot to whoever owns the application (you), which is the easy way. To do it
by hand, or to let a few friends in, put user IDs in `.env`:

```
ALLOWED_USER_IDS=123456789012345678,234567890123456789
```

To get your ID: Discord Settings → Advanced → turn on **Developer Mode**, then right click your name
→ **Copy User ID**. Everybody else gets told to go run their own.
