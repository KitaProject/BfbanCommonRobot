from pydantic import BaseModel


class ServerListConfig(BaseModel):
    data_source_host: str


class BfbanConfig(BaseModel):
    bfban_host: str | None = "https://bfban.gametools.network"
    captcha_host: str | None = None
    captcha_host_auth: str | None = None
    date_source_host: str
    bfban_token: str | None
    image_host_auth: str


class PluginConfig(BaseModel):
    server_list: ServerListConfig
    bfban: BfbanConfig


class Account(BaseModel):
    qq_id: int
    admin_qq_ids: list[int]
    verifyKey: str
    mirai_host: str


class AppConfig(BaseModel):
    account: Account
    plugins: PluginConfig
    version: str
