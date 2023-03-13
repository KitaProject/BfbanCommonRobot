import asyncio
import json
from io import BytesIO
from json import JSONDecodeError
from typing import Literal

from PIL import Image
from aiohttp import FormData
from graia.ariadne import Ariadne
from apps.bfban.interface import AbstractQueryClient, PlayerNotFoundException, AbstractImageDataBase, ImageException, \
    AbstractTokenManager
from apps.bfban.models import AllStatusModel
from configs import bot_config

_all_status_cache = {}


async def _clear_cache():
    with True:
        await asyncio.sleep(60 * 5)
        _all_status_cache.clear()


class QueryClient(AbstractQueryClient):
    _task = None
    clear_flag = False

    async def query_player_all_stats(self, game: Literal["bf1", "bfv", "bf2042"], ea_id: str,
                                     pid: int) -> AllStatusModel:
        assert isinstance(ea_id, str)
        if game != "bfv":
            raise NotImplemented

        if not QueryClient.clear_flag:
            # lazy start
            QueryClient.clear_flag = True
            QueryClient._task = asyncio.create_task(_clear_cache())

        if ea_id.lower() in _all_status_cache:
            return _all_status_cache.get(ea_id.lower())

        async with Ariadne.service.client_session.get(
                url=f"{bot_config.plugins.bfban.date_source_host}/api/v2/bfv/status/all/fast",
                params={"name": ea_id, "pid": pid}) as response:
            res_text = await response.text()
            if response.status != 200:
                # retry
                await asyncio.sleep(2)
                async with Ariadne.service.client_session.get(
                        url=f"{bot_config.plugins.bfban.date_source_host}/api/v2/bfv/status/all/fast",
                        params={"name": ea_id, "pid": pid}) as response_retry:
                    res_text = await response_retry.text()
            try:
                res = json.loads(res_text)
            except JSONDecodeError:
                from loguru import logger
                logger.exception("failed to get player info:")
            if "detail" in res and res["detail"] == "player not found":
                raise PlayerNotFoundException(f"{ea_id} not found")

            data = AllStatusModel(**res)
            _all_status_cache[ea_id.lower()] = data
            return data

    async def query_player_pid(self, ea_id: str) -> int:
        assert isinstance(ea_id, str)

        async with Ariadne.service.client_session.get(
                f"{bot_config.plugins.bfban.date_source_host}/api/v2/pid/fast",
                params={"name": ea_id}
        ) as response:
            res = await response.json()
            if not res.get("exist", False):
                raise PlayerNotFoundException(f"{ea_id} not found")
            pid = res["pid"]
            return pid

    async def query_player_bfban_stats(self, pid: int) -> str:
        assert isinstance(pid, int)

        async with Ariadne.service.client_session.get(
                url=f"{bot_config.plugins.bfban.bfban_host}/api/player",
                params={"personaId": pid}) as response:
            res = await response.json()
            if res["code"] != "player.ok":
                return "未被举报"

            status: int = int(res["data"]["status"])

            bfban_status = self.status_mapper.get(status, "查询失败")
            return bfban_status


def compress_image(image_bytes: bytes) -> bytes:
    image_content = BytesIO(image_bytes)
    image = Image.open(image_content)
    image = image.convert('RGB')

    bio = BytesIO()
    image.save(bio, format="JPEG", quality=72)

    return bio.getvalue()


class SmmsImageDataBase(AbstractImageDataBase):
    _base_url_endpoints: str = "https://smms.app/api/v2"
    _headers = {
        # "Content-Type": "multipart/form-data",
        "Authorization": str(bot_config.plugins.bfban.image_host_auth)
    }

    async def upload_image(self, image: bytes | BytesIO) -> str:

        if isinstance(image, bytes):
            raw_image = image
        elif isinstance(image, BytesIO):
            image.seek(0)
            raw_image = image.read()
        else:
            raise ValueError("image must be a bytes or BytesIO")

        if len(raw_image) > 1024 * 1024:
            raw_image = compress_image(raw_image)

        image_data = FormData()
        image_data.add_field("smfile", raw_image)

        async with Ariadne.service.client_session.post(
                url=f"{self._base_url_endpoints}/upload",
                data=image_data,
                headers=self._headers
        ) as response:
            res = await response.json()

            if res["success"]:
                return res["data"]["url"]
            elif res["code"] == "image_repeated":
                rsp_msg = str(res["message"])
                start = rsp_msg.find("https:")
                return rsp_msg[start:]
            elif "Flood detected" in res["message"]:
                raise ImageException("超出图片限额")
            else:
                raise ImageException(f"ERROR: {res['message']}")


class BfbanTokenManager(AbstractTokenManager):

    async def get_bfban_token(self, *args, **kwargs) -> str:
        async with Ariadne.service.client_session.get(
                url=f"{bot_config.plugins.bfban.date_source_host}/api/v2/bfban/token?type=bfban_token") as response:
            res = await response.json()
            # logger.info("bfban token:", res["data"])
            return res["data"]
