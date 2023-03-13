import json
import os

from configs.models import AppConfig

with open(f"{os.path.dirname(os.path.abspath(__file__))}/config.json", "r", encoding="utf-8") as file:
    _config_data = json.load(file)
    bot_config: AppConfig = AppConfig(**_config_data)


