# BOT-CTelegram

This bot copy all content from **source** channel to **destination** chaneel (or chat)

It worte base on **Pyrogram** that is a modern, elegant and asynchronous **MTProto** API framework

There is **big difference** between this bot and many other telegram bot chat copyer
They read the messages using a client and then send the messages to the channel with the **same client** again but in this but we read the message with cleint and send them with a api bot
- api bots have not significant limit on sending messages,so We get rid of the problem of temporary limitation of sending messages with the client.
- and also We can add inline_button for messages, this feature is only for api bots and a client user can't.

> Welcome to join in and feel free to contribute.

#### Futures
* make copy all type of message from source to destination.
* It support multi client.
* If a message is deleted in the source channel, it will also be deleted in the destination channel.
* If a message is edited in the source channel, it will also be edited in the destination channel.
* If a message is pinned or unpinned in the source channel, it will also be pinned or unpinned in the destination channel.
* IF profile picture is changed in the source channel, profile picture will be set in the destination channel as well.
* If a message has inelie_button, it will be sent to the destination channel with the same inelie_button.

#### Installation
* You need Python >= 3.7
* pip install -r requirements.txt
* make config right config.py
* python main.py (run on the screen)


#### Admin API bot command
* /id
* /add
* /del
* /channels

#### Example


```bash
/add
phone number |source chat id|destination chat id
+989121111111|-1000000000001|-1000000000002
+989121111111|-1000000000003|-1000000000004
+989122222222|-1000000000003|-1000000000004
```