# Deployment

### Clone the repo

```
$ git clone https://github.com/engfrosh/discord-bot.git
$ git submodule init
$ git submodule update
$ pip install -r requirements.txt
```

update the database credentials

Add it as a service.
Add to `/etc/systemd/system/engfrosh_bot.service`
```
[Unit]
Description=EngFrosh Discord Bot
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/discord-bot
ExecStart=python3 -m bot
EnvironmentFile=/etc/engfrosh_site_environment

[Install]
WantedBy=multi-user.target
```

Then run
```
systemctl start engfrosh_bot
```
and check that the bot is indeed running
```
systemctl enable engfrosh_bot
```
so that it runs at start up.