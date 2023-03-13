import pkgutil

from graia.ariadne.app import Ariadne
from graia.ariadne.connection.config import (
    HttpClientConfig,
    WebsocketClientConfig,
    config,
)
from graia.ariadne.event.message import GroupMessage

from graia.broadcast import Broadcast
from graia.saya import Saya
from creart import create
from configs import bot_config

bcc = create(Broadcast)

app = Ariadne(
    connection=config(
        bot_config.account.qq_id,
        bot_config.account.verifyKey,
        WebsocketClientConfig(host=f"ws://{bot_config.account.mirai_host}"),
        HttpClientConfig(host=f"http://{bot_config.account.mirai_host}"),
    ),
)



saya = create(Saya)

with saya.module_context():
    for module in pkgutil.iter_modules(["modules"]):
        if not module.name.startswith("_"):
            saya.require(f"modules.{module.name}")

if __name__ == '__main__':
    app.launch_blocking()
