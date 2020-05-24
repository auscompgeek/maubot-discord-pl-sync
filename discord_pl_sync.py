# discord_pl_sync - A maubot plugin to map Discord roles to Matrix power levels
# Copyright (C) 2020 David Vo
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

from typing import Dict, List, Optional, Type, TypedDict

from maubot import MessageEvent, Plugin
from maubot.handlers import command, event
from mautrix.types import (
    EventType,
    MemberStateEventContent,
    PowerLevelStateEventContent,
    RoomID,
    StateEvent,
    UserID,
)
from mautrix.util.config import BaseProxyConfig, ConfigUpdateHelper


class DiscordRole(TypedDict):
    color: int
    name: str
    position: int


class DiscordMember(TypedDict):
    bot: bool
    displayColor: int
    id: str
    roles: List[DiscordRole]
    username: str


class Config(BaseProxyConfig):
    def do_update(self, helper: ConfigUpdateHelper) -> None:
        helper.copy("rooms")
        helper.copy("server_name")
        helper.copy("allow_manual_resync")


class DiscordRolePLSync(Plugin):
    @classmethod
    def get_config_class(cls) -> Type[BaseProxyConfig]:
        return Config

    async def start(self) -> None:
        self.config.load_and_update()
        self.power_level_cache: Dict[RoomID, PowerLevelStateEventContent] = {}

    async def get_power_levels(self, room_id: RoomID) -> PowerLevelStateEventContent:
        levels = self.power_level_cache.get(room_id)
        if not levels:
            levels = await self.client.get_state_event(
                room_id, EventType.ROOM_POWER_LEVELS
            )
            self.power_level_cache[room_id] = levels
        return levels

    @event.on(EventType.ROOM_POWER_LEVELS)
    async def handle_power_levels(self, evt: StateEvent) -> None:
        room_id = evt.room_id
        if room_id not in self.config["rooms"]:
            return
        self.power_level_cache[room_id] = evt.content

    @event.on(EventType.ROOM_MEMBER)
    async def handle_membership(self, evt: StateEvent) -> None:
        room_id = evt.room_id
        mxid = UserID(evt.state_key)
        # If this is us, then we should invalidate the PL cache for this room
        if mxid == self.client.mxid:
            self.power_level_cache.pop(room_id, None)
            return

        if not self._is_discord_ghost(mxid):
            return

        role_pl = self._find_desired_pl(room_id, evt.content)
        if role_pl is not None:
            self.log.info("Set PL in %s of %s to %s", room_id, mxid, role_pl)

            pls = await self.get_power_levels(room_id)
            if pls.get_user_level(mxid) == role_pl:
                self.log.info("%s %s PL already %s", room_id, mxid, role_pl)
                await evt.mark_read()
            else:
                pls.set_user_level(mxid, role_pl)
                await self.client.send_state_event(
                    room_id, EventType.ROOM_POWER_LEVELS, pls
                )

    @command.new("syncdiscordroles")
    @command.argument("room_id")
    async def sync_roles(self, evt: MessageEvent, room_id: RoomID) -> None:
        if not self.config["allow_manual_resync"]:
            evt.respond("Manual Discord role resync is disabled.")
            return

        if room_id not in self.config["rooms"]:
            evt.respond("That room is not in my config.")
            return

        power_levels = await self.get_power_levels(room_id)
        members = await self.client.get_members(room_id)
        pls_changed = False

        for member in members:
            mxid = UserID(member.state_key)
            if not self._is_discord_ghost(mxid):
                continue

            role_pl = self._find_desired_pl(room_id, member.content)
            if role_pl is not None:
                power_levels.set_user_level(mxid, role_pl)
                pls_changed = True

        if pls_changed:
            await self.client.send_state_event(
                room_id, EventType.ROOM_POWER_LEVELS, power_levels
            )

        await evt.mark_read()

    def _is_discord_ghost(self, mxid: UserID) -> bool:
        """Checks if a given Matrix user is from our Discord bridge instance."""
        return (
            mxid.startswith("@_discord_")
            and mxid.endswith(":" + self.config["server_name"])
        )

    def _find_desired_pl(
        self, room_id: RoomID, member: MemberStateEventContent,
    ) -> Optional[int]:
        role_map: Optional[Dict[str, int]] = self.config["rooms"].get(room_id)
        if not role_map:
            return None

        user: Optional[DiscordMember] = member.get("uk.half-shot.discord.member")
        # Ensure we have information about the Discord user's roles.
        # We won't have this for the event generated by a profile update,
        # or if membership is not join.
        if user is None:
            return None

        user_roles: List[DiscordRole] = user["roles"]
        for role in sorted(user_roles, key=lambda role: -role["position"]):
            role_pl = role_map.get(role["name"])
            if role_pl is not None:
                self.log.debug("Found role %s in %s", role["name"], room_id)
                return role_pl

        return None
