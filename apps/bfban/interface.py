from abc import ABC, abstractmethod
from io import BytesIO
from typing import Literal
from apps.bfban.models import AllStatusModel


class ImageException(Exception):
    pass


class QueryException(Exception):
    pass


class PlayerNotFoundException(QueryException):
    pass


class AbstractImageDataBase(ABC):

    @abstractmethod
    async def upload_image(self, image: bytes | BytesIO) -> str:
        pass


class AbstractQueryClient(ABC):
    status_mapper = {
        -1: "未被举报",
        0: "未处理",
        1: "石锤",
        2: "待自证",
        3: "MOSS自证",
        4: "无效举报",
        5: "讨论中",
        6: "即将石锤",
        7: "查询失败",
        8: "刷枪",
        9: "申诉中"
    }

    @abstractmethod
    async def query_player_all_stats(self, game: Literal["bf1", "bfv", "bf2042"], ea_id: str,
                                     pid: int) -> AllStatusModel:
        pass

    @abstractmethod
    async def query_player_pid(self, ea_id: str) -> int:
        pass

    @abstractmethod
    async def query_player_bfban_stats(self, pid: int) -> str:
        pass


class AbstractTokenManager(ABC):

    @abstractmethod
    async def get_bfban_token(self, *args, **kwargs) -> str:
        pass
