from discord.ext import commands, ipc
from discord.ext.ipc.objects import ClientPayload
from discord.ext.ipc.server import Server
from discord.utils import get_or_fetch

from config import IPC_SECRET
from utils import Bot, CustomLogger, StatTypeEnum


class IPC(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)
        self.ipc = ipc.Server(self.client, secret_key=IPC_SECRET)

    @Server.route("/get_user_stats")
    async def get_user_stats(self, data: ClientPayload) -> dict:
        try:
            user = await get_or_fetch(self.client, "user", id=data.user_id)
        except:
            return {"error": "User does not exist", "status": 404}
        user_voice_time = await self.client.db.get_user_stat(user, StatTypeEnum.VoiceTime, None)
        commands_used = await self.client.db.get_user_stat(user, StatTypeEnum.CommandsUsed, None)
        messages_sent = await self.client.db.get_user_stat(user, StatTypeEnum.MessagesSent, None)
        if user_voice_time is None and commands_used is None and messages_sent is None:
            return {"error": "User has no stats", "status": 404}
        else:
            resp = {"user": user._to_minimal_user_json()}
            for stat_list in [user_voice_time, commands_used, messages_sent]:
                if stat_list is not None:
                    for value in stat_list:
                        if str(value[3]) not in resp:
                            resp[str(value[3])] = {}
                        resp[str(value[3])][str(value[1])] = value[2]
            return resp

    @commands.Cog.listener("on_start_done")
    async def on_start_done(self):
        self.logger.info("IPC server started")
        await self.client.ipc.start()

    @commands.Cog.listener("on_ipc_error")
    async def on_ipc_error(self, endpoint: str, error: Exception):
        self.logger.error(f"IPC Endpoint {endpoint} raised: {error}")
        raise error


def setup(client):
    client.add_cog(IPC(client))
