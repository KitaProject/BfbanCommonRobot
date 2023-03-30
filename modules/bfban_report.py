import asyncio
import re
from typing import Sequence

from creart import create
from graia.amnesia.message import MessageChain
from graia.ariadne import Ariadne
from graia.ariadne.event.message import GroupMessage
from graia.ariadne.message import Source
from graia.ariadne.message.element import Plain
from graia.ariadne.message.parser.twilight import Twilight, UnionMatch, SpacePolicy, ParamMatch, RegexResult
from graia.ariadne.model import Group, Member
from graia.broadcast import ExecutionStop
from graia.broadcast.interrupt import InterruptControl
from graia.saya import Channel, Saya
from graia.saya.builtins.broadcast import ListenerSchema
from apps.bfban.implement import QueryClient
from apps.bfban.interface import AbstractQueryClient, PlayerNotFoundException
from apps.bfban.report_step import (ImageStepWaiter, BasicStepWaiter, SelectStepWaiter, Steps,
                                    WaiterResult, CollectStepWaiter, report_sessions, ReportContex, CaptchaStepWaiter)
import contextlib
from loguru import logger

saya = Saya.current()
channel = Channel.current()
inc = create(InterruptControl)

command_rule = Twilight(UnionMatch("!", "！", ".", "。").space(SpacePolicy.NOSPACE),
                        UnionMatch("report", "举报").space(SpacePolicy.PRESERVE),
                        "ea_id" @ ParamMatch())


async def response_handle(ret_code, ret_content, app: Ariadne, contact: Group, source: Source, ea_id: str):
    if ret_content is None:
        ret_content = []
    if not (isinstance(ret_content, Sequence) or isinstance(ret_content, MessageChain)):
        ret_content = list(ret_content)
    match ret_code:
        case Steps.CANCEL:
            await app.send_message(contact, MessageChain([Plain(f"{ret_code}\n你取消了对\"{ea_id}\"的举报")]).extend(
                ret_content), quote=source)
            report_sessions.remove(ea_id)
            raise ExecutionStop
        case Steps.FAILED:
            await app.send_message(contact, MessageChain([Plain(f"{ret_code}\n")]).extend(ret_content), quote=source)
            report_sessions.remove(ea_id)
            raise ExecutionStop
        case Steps.ERROR:
            await app.send_message(contact, MessageChain([Plain(f"{ret_code}\n")]).extend(ret_content), quote=source)
            report_sessions.remove(ea_id)
            raise ExecutionStop
        case Steps.RETRY:
            await app.send_message(contact, MessageChain([Plain(f"{ret_code}\n")]).extend(ret_content), quote=source)
        case Steps.CONTINUE:
            await app.send_message(contact, MessageChain([Plain(f"{ret_code}\n")]).extend(ret_content), quote=source)
        case Steps.SUCCEED:
            await app.send_message(contact, MessageChain([Plain(f"{ret_code}\n")]).extend(ret_content), quote=source)
            report_sessions.remove(ea_id)


@channel.use(ListenerSchema(listening_events=[GroupMessage], inline_dispatchers=[command_rule]))
async def on_report(app: Ariadne, contact: Group, sender: Member, source: Source, ea_id: RegexResult):
    ea_id = str(ea_id.result)

    @contextlib.asynccontextmanager
    async def step_waiter_ctx_manager(basic_waiter: type[BasicStepWaiter], ctx: ReportContex):
        try:
            waiter_result: WaiterResult = await inc.wait(basic_waiter(app, contact.id, sender.id, ctx), timeout=150)
            ret_code = waiter_result.code
            ret_content = waiter_result.content
            ret_res = waiter_result.data
            ret_source = waiter_result.source
            await response_handle(ret_code, ret_content, app, contact, ret_source, ea_id)
            yield ret_code, ret_res

        except asyncio.TimeoutError:
            await response_handle(Steps.CANCEL, "举报会话已超时，请重新发起举报", app, contact, source, ea_id)
            raise ExecutionStop

    if not re.match(r"[a-zA-Z\-_\d]{4,32}", ea_id):
        await response_handle(Steps.FAILED, "请输入正确的游戏ID，不需要输入战队名", app, contact, source, ea_id)
        return

    await app.send_message(contact, f'正在获取ID"{ea_id}"的信息喵', quote=source)

    query_client: AbstractQueryClient = QueryClient()
    try:
        pid = await query_client.query_player_pid(ea_id)
    except PlayerNotFoundException:
        await response_handle(Steps.FAILED, "此ID不存在，请确认此玩家最新的游戏ID", app, contact, source, ea_id)
        return

    bfban_status: str | None = "查询超时"

    try:
        bfban_status = await asyncio.wait_for(query_client.query_player_bfban_stats(pid), 7)
    except BaseException as e:
        logger.exception("bfban状态获取失败", e)

    if bfban_status is not None:
        if bfban_status not in ("查询失败", "未被举报", "查询超时"):
            bfban_case = f"链接： https://bfban.gametools.network/player/{pid} "
            # bfban_case = f" "
            if bfban_status in ("石锤", "即将石锤"):
                await response_handle(Steps.FAILED,
                                      f'此玩家"{ea_id}"当前状态为"{bfban_status}"\n{bfban_case}\n感谢你对游戏做出的贡献',
                                      app, contact, source, ea_id)
            else:
                await response_handle(Steps.CONTINUE,
                                      f'此玩家"{ea_id}"当前状态为"{bfban_status}"\n{bfban_case}\n若要补充证据请按照提示继续',
                                      app, contact, source, ea_id)

    async with report_sessions.lock:
        if ea_id in report_sessions:
            await response_handle(Steps.FAILED,
                                  f"{report_sessions[ea_id].reporter_id}正在进行举报此ID的会话，请勿重复提交",
                                  app, contact, source, ea_id)
            return
        else:
            contex = ReportContex(ea_id, pid, sender.id, contact.id)
            report_sessions[ea_id] = contex

    await app.send_message(contact, "请输入要举报的游戏（战地1、战地5或2042）", quote=source)
    while True:
        async with step_waiter_ctx_manager(SelectStepWaiter, contex) as waiter_res:
            code, res = waiter_res
        if code != Steps.RETRY:
            break
    contex.game_type = res

    while True:
        async with step_waiter_ctx_manager(ImageStepWaiter, contex) as waiter_res:
            code, res = waiter_res
        if code != Steps.RETRY:
            break

    await app.send_message(contact,
                           f"请输入举报的详细信息，视频请先上传至bilibili等网站后，再回复视频链接。请不要在没有客观证据下凭借主观意识随意举报",
                           quote=source)

    while True:
        async with step_waiter_ctx_manager(CollectStepWaiter, contex) as waiter_res:
            code, res = waiter_res
        if code != Steps.RETRY:
            break

    while True:
        async with step_waiter_ctx_manager(CaptchaStepWaiter, contex) as waiter_res:
            code, res = waiter_res
        if code != Steps.RETRY:
            break
