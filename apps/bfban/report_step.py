import asyncio
import contextlib
import random
import re
import time
from asyncio import Task
from base64 import b64encode
from enum import StrEnum
from typing import Coroutine, ClassVar

from graia.ariadne import Ariadne
from graia.ariadne.message.element import Image, MultimediaElement, Plain
from graia.broadcast.builtin.decorators import Depend
from abc import ABC, abstractmethod

from apps.bfban import svg
from apps.bfban.implement import SmmsImageDataBase, BfbanTokenManager, QueryClient
from apps.bfban.interface import AbstractImageDataBase, ImageException, AbstractTokenManager, AbstractQueryClient, \
    QueryException
from apps.bfban.models import AllStatusModel
from configs import bot_config
from collections import namedtuple
from graia.amnesia.message import MessageChain
from graia.ariadne.event.message import GroupMessage
from graia.ariadne.message import Source
from graia.ariadne.model import Member, Group
from graia.broadcast import ExecutionStop
from graia.broadcast.interrupt import Waiter
from loguru import logger

WaiterResult = namedtuple('WaiterResult', ['code', 'content', 'data', 'source'])


class Steps(StrEnum):
    ERROR = "[report error]"
    FAILED = "[report failed]"
    CANCEL = "[report cancel]"
    RETRY = "[report retry]"
    CONTINUE = "[report continue]"
    SUCCEED = "[report succeed]"


class ReportCancel(Exception):
    pass


class ReportContex:
    def __init__(self, target_player: str, target_pid: int, reporter_id: int, contact_id: int):
        self.target_player_ea_id: str = target_player
        self.target_pid: int = target_pid
        self.reporter_id: int = reporter_id
        self.contact_id: int = contact_id
        self.target_info: AllStatusModel | None = None
        self.description_list: list[str] = []
        self.description_img_list: list[str] = []
        self.game_type: str | None = None
        self.captcha_encrypt: str | None = None
        self.captcha: str | None = None
        self.captcha_url: str | None = None
        self.captcha_img: Image | None = None

    @property
    def description(self) -> str:
        head = f"<p>This report comes from common robots (source group: " + \
               f"{str(self.contact_id)[:4]}{'*' * (len(str(self.contact_id)) - 4)}" + \
               f"at: {time.strftime('%Y-%m-%d %H:%M')})</p><br>BOT共获取到以下玩家数据信息：<br><br>"

        stats = "获取失败" if self.target_info is None else self.target_info.get_stats_info()

        body = "<br>".join(self.description_list)

        img = ""

        for item in self.description_img_list:
            img = img + f'<img src="{item}">'

        return f"{head}{stats}<br>以下为玩家提供的举报信息：<br><br>{body}{img}"

    def add_description(self, description: str):
        self.description_list.append(description)

    @property
    def report_body(self) -> dict:
        report_body = {
            "data": {
                "game": f"{self.game_type}",
                "originName": f"{self.target_player_ea_id}",
                "cheatMethods": [
                    "wallhack"
                ],
                "videoLink": "",
                "description": f"{self.description}"
            },
            "encryptCaptcha": f"{self.captcha_encrypt}",
            "captcha": f"{self.captcha}"
        }

        return report_body

    async def do_report(self) -> str:
        # logger.info(f"do report, report body:\n{self.report_body}")
        # return "test"
        async with Ariadne.service.client_session.post(
                url=f"{bot_config.plugins.bfban.bfban_host}/api/player/report",
                headers={"x-access-token": await report_sessions.token},
                json=self.report_body) as response:
            res = await response.json()

            return res["code"]


class ReportSessions:
    _sessions: dict[str, ReportContex] = {}
    _token: ClassVar[str | None] = None
    _token_lock: asyncio.Lock = asyncio.Lock()
    lock: asyncio.Lock = asyncio.Lock()
    token_manager: AbstractTokenManager = BfbanTokenManager()
    _task: Task | None = None

    def __contains__(self, item: str):
        assert isinstance(item, str)
        return str(item).lower() in self._sessions

    def __getitem__(self, item: str):
        assert isinstance(item, str)
        if str(item).lower() not in self._sessions:
            raise KeyError(f"not fount target {item}")
        return self._sessions[str(item).lower()]

    def __setitem__(self, key: str, value: ReportContex):
        assert isinstance(key, str) and isinstance(value, ReportContex)
        self._sessions[key.lower()] = value

    def remove(self, target_name: str):
        assert isinstance(target_name, str)
        if target_name.lower() in self._sessions:
            del self._sessions[target_name.lower()]

    async def update_token_task(self):
        while True:
            try:
                async with self._token_lock:
                    ReportSessions._token = await self.token_manager.get_bfban_token()
            except BaseException as e:
                logger.exception(e)
            await asyncio.sleep(60 * 30)

    @property
    async def token(self) -> str:
        if ReportSessions._task is None:
            async with self._token_lock:
                if ReportSessions._token is None and ReportSessions._task is None:
                    ReportSessions._token = await self.token_manager.get_bfban_token()
                    ReportSessions._task = asyncio.create_task(self.update_token_task())
        async with self._token_lock:
            return str(ReportSessions._token)


report_sessions = ReportSessions()


class BasicStepWaiter(Waiter, ABC):
    listening_events = [GroupMessage]
    using_dispatchers = None
    priority = 14
    block_propagation = True

    def __init__(self, app: Ariadne, contact: int, sender: int, report_ctx: ReportContex):
        self.contact: int = contact
        self.sender: int = sender
        self.app: Ariadne = app
        self.using_decorators = [self.check_operator_permission()]
        self.report_ctx = report_ctx

    @abstractmethod
    async def on_event_detected(self, group: Group, member: Member, message: MessageChain, source: Source):
        pass

    async def detected_event(self, group: Group, member: Member, message: MessageChain, source: Source):
        try:
            self.check_cancel(message)
        except ReportCancel:
            return WaiterResult(Steps.CANCEL, None, None, source)

        async with self.catcher(self.on_event_detected(group, member, message, source)) as res:
            return res

    def check_sender(self, group: Group, member: Member):
        if self.contact != group.id or self.sender != member.id:
            raise ExecutionStop

    def check_operator_permission(self):
        async def check_sender_deco(group: Group, member: Member):
            if self.contact != group.id or self.sender != member.id:
                raise ExecutionStop

        return Depend(check_sender_deco)

    @staticmethod
    def check_cancel(message: MessageChain):
        if str(message) == "取消":
            raise ReportCancel()

    async def exception_handle(self, raw_ex):
        pass

    @contextlib.asynccontextmanager
    async def catcher(self, coroutine: Coroutine):
        try:
            res = await coroutine
            yield res
        except BaseException as e:
            logger.exception(e)
            yield WaiterResult(Steps.ERROR, f"发生了未捕获的异常: {str(e)}", None, None)
            await self.exception_handle(e)


class SelectStepWaiter(BasicStepWaiter):

    async def on_event_detected(self, group: Group, member: Member, message: MessageChain, source: Source):

        match str(message).lower():
            case "1" | "一" | "战地1" | "战地一" | "bf1":
                return WaiterResult(Steps.CONTINUE, "请输入举报的图片，受服务器容量限制暂只支持一张", "bf1", source)
            case "5" | "五" | "战地5" | "战地五" | "bf5":

                try:
                    query_client: AbstractQueryClient = QueryClient()
                    await self.app.send_message(group, f"正在获取玩家游戏数据快照", quote=source)
                    stats = await query_client.query_player_all_stats("bfv", self.report_ctx.target_player_ea_id,
                                                                      self.report_ctx.target_pid)
                    self.report_ctx.target_info = stats
                except QueryException as e:
                    logger.exception(e)

                return WaiterResult(Steps.CONTINUE, "请输入举报的图片，受服务器容量限制暂只支持一张", "bfv", source)
            case "2042" | "战地2042" | "bf2042":
                return WaiterResult(Steps.CONTINUE, "请输入举报的图片，受服务器容量限制暂只支持一张", "bf6", source)
            case _:
                return WaiterResult(Steps.RETRY, "请输入正确的游戏名", None, source)

    def __init__(self, app: Ariadne, group: Group | int, member: Member | int, report_ctx: ReportContex):
        super().__init__(app, group, member, report_ctx)


class ImageStepWaiter(BasicStepWaiter):

    async def on_event_detected(self, group: Group, member: Member, message: MessageChain, source: Source):

        if str(message) == "无":
            return WaiterResult(Steps.CONTINUE, f"跳过了图片上传", None, source)

        if Image not in message:
            return WaiterResult(Steps.RETRY, f"请发送图片消息，回复\"无\"以跳过上传，回复\"取消\"放弃", None, source)
        else:
            await self.app.send_message(group, [f"正在上传图片"], quote=source)
            image: Image = message.get(Image)[0]
            data = await image.get_bytes()

            image_db: AbstractImageDataBase = SmmsImageDataBase()
            try:
                url = await image_db.upload_image(data)
            except ImageException as e:
                return WaiterResult(Steps.CONTINUE, f"图片上传失败，错误信息：{e}", None, source)

            self.report_ctx.description_img_list.append(url)

            return WaiterResult(Steps.CONTINUE, f"图片上传成功", url, source)

    def __init__(self, app: Ariadne, group: Group | int, member: Member | int, report_ctx: ReportContex):
        super().__init__(app, group, member, report_ctx)


class CollectStepWaiter(BasicStepWaiter):

    async def on_event_detected(self, group: Group, member: Member, message: MessageChain, source: Source):

        if MultimediaElement in message:
            return WaiterResult(Steps.RETRY, rf"不支持的消息类型，请发送举报的文字信息", None, source)

        reasons = str(message)

        if len(reasons) < 12:
            return WaiterResult(Steps.RETRY,
                                rf"请输入更详细的举报信息，图片可能会失效，所以请不要只依靠图片来描述举报信息。" +
                                rf"如若涉及具体的对局请至 https://battlefieldtracker.com" +
                                rf"/{self.report_ctx.game_type}/profile" +
                                rf"/origin/{self.report_ctx.target_player_ea_id}/gamereports " +
                                rf"查询游戏战报后附加在举报内容中",
                                None, source)

        reasons = list(map(lambda x: f"<p>{x}</p>", reasons.split("\n")))

        self.report_ctx.description_list.extend(reasons)

        await self.app.send_message(group, [f"正在获取验证码"], quote=source)

        try:
            svg_data = await self.get_captcha_svg_data()
        except BaseException as e:
            logger.exception(e)
            try:
                svg_data = await self.get_captcha_svg_data()
            except BaseException as e:
                logger.exception(e)
                return WaiterResult(Steps.ERROR, rf"验证码获取失败", None, source)

        bio = await asyncio.to_thread(svg.str_svg_2_png, svg_data)

        img = Image(data_bytes=bio.getvalue())
        base64_str = b64encode(bio.getvalue()).decode("ascii")

        self._task = asyncio.create_task(self.upload_captcha_img_task(base64_str, group, source))

        self.report_ctx.captcha_img = img
        return WaiterResult(Steps.CONTINUE, MessageChain([Plain("请输入验证码以提交举报\n"), img]),
                            str(message), source)

    def __init__(self, app: Ariadne, group: Group | int, member: Member | int, report_ctx: ReportContex):
        super().__init__(app, group, member, report_ctx)
        self._task = None

    async def get_captcha_svg_data(self) -> str:
        from graia.ariadne import Ariadne

        async with Ariadne.service.client_session.get(url=f"{bot_config.plugins.bfban.bfban_host}/api/captcha",
                                                      params={"t": random.random()}) as response:
            res = await response.json()
            self.report_ctx.captcha_encrypt = res["data"]["hash"]
            return res["data"]["content"]

    async def upload_captcha_img_task(self, img_base64: str, contact, source):
        try:
            if bot_config.plugins.bfban.captcha_host is not None:
                self.report_ctx.captcha_url = await self.upload_captcha_img(img_base64)
        except BaseException as e:
            logger.exception(e)

        if self.report_ctx.captcha_url is not None:
            await self.app.send_message(contact,
                                        [f"若验证码图片发送失败请手动查看:\n{self.report_ctx.captcha_url}"],
                                        quote=source)

    async def upload_captcha_img(self, img_b64: str) -> str:
        captcha_id = str(abs(hash(img_b64)))
        from graia.ariadne import Ariadne
        async with Ariadne.service.client_session.post(url=f"{bot_config.plugins.bfban.captcha_host}",
                                                       params={"captcha_id": captcha_id},
                                                       json={
                                                           "auth": f"{bot_config.plugins.bfban.captcha_host_auth}",
                                                           "captcha_code": f"{img_b64}"
                                                       }) as response:
            res = await response.json()
            if res["result"] != "ok":
                raise ImageException("验证码上传失败")
            return f"{bot_config.plugins.bfban.captcha_host}/?captcha_id={captcha_id}"


class CaptchaStepWaiter(BasicStepWaiter):

    async def on_event_detected(self, group: Group, member: Member, message: MessageChain, source: Source):

        if MultimediaElement in message:
            return WaiterResult(Steps.RETRY, rf"不支持的消息类型，请输入验证码", None, source)

        captcha = str(message)
        if re.match("([a-z]|[A-Z]|[0-9]){4}", captcha) is None:
            return WaiterResult(Steps.RETRY, rf"请输入正确的验证码", None, source)
        self.report_ctx.captcha = captcha

        try:
            response_code: str = await self.report_ctx.do_report()
        except BaseException as e:
            logger.exception(e)
            return WaiterResult(Steps.ERROR, f"糟糕！举报失败，连接BFBAN服务器发生错误", None, source)

        match response_code:
            case "report.success":
                return WaiterResult(Steps.SUCCEED,
                                    f'举报"{self.report_ctx.target_player_ea_id}"成功\n' +
                                    f'案件链接：https://bfban.gametools.network/player/{self.report_ctx.target_pid}\n' +
                                    f'感谢你对游戏做出的贡献喵\n'
                                    + f'存在问题请提交issues：https://github.com/KitaProject/BfbanCommonRobot/issues'
                                    , None, source)
            case "captcha.wrong":
                return WaiterResult(Steps.RETRY, ['验证码输入错误，请重新输入', self.report_ctx.captcha_img], None,
                                    source)
            case "user.tokenExpired":
                return WaiterResult(Steps.FAILED,
                                    f'糟糕！举报"{self.report_ctx.target_player_ea_id}"失败，当前机器人登陆状态异常',
                                    None, source)
            case _:
                return WaiterResult(Steps.ERROR,
                                    f'糟糕！举报"{self.report_ctx.target_player_ea_id}"失败，' +
                                    f'BFBAN接口返回的错误信息：{response_code}',
                                    None, source)

    def __init__(self, app: Ariadne, group: Group | int, member: Member | int, report_ctx: ReportContex):
        super().__init__(app, group, member, report_ctx)
