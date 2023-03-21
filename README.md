# BfbanCommonRobot


<div align="center">

A QQ robot based on [Ariadne](https://github.com/GraiaProject/Ariadne) for the battlefield anti-cheat website [BFBAN](https://bfban.gametools.network).

一款基于 [Ariadne](https://github.com/GraiaProject/Ariadne) 的QQ机器人，用于Battlefield 系列游戏反作弊网站 [BFBAN](https://bfban.gametools.network).

Python Version of requirement:
![Python Version](https://img.shields.io/badge/python-v3.11-blue) 

本项目以 `GPLv3` 作为开源协议, 这意味着你需要遵守相应的规则.

</div>



## 安装与运行

1. `git clone https://github.com/KitaProject/BfbanCommonRobot.git` 或 Download ZIP

2. `pip3 install -r ./requirements.txt` 或 `poetry install`

3. 安装并配置 [Mirai](https://github.com/project-mirai/mirai-api-http) 

4. 编辑 configs/config.json
```json

{
  "account": {
    "qq_id": 54321,
    "admin_qq_ids": [
      12345
    ],
    "verifyKey": "Mirai-Api-Http秘钥",
    "mirai_host": "Mirai-Api-Http监听地址"
  },
  "plugins": {
    "server_list": {
      "data_source_host": ""
    },
    "bfban": {
      "bfban_host": "https://bfban.gametools.network",
      "date_source_host": "数据源地址",
      "bfban_token": "BFBAN账号Token（暂未实现）",
      "image_host_auth": "sm.ms图床AuthToken"
    }
  },
  "version": "0.1.1-dev"
}
```

5. `python3 main.py`
