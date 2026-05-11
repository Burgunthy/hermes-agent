"""
Profile-based routing for the gateway.

Allows a single gateway instance to route specific channels/threads to
different Hermes profiles, each with their own model, tools, memory, and
persona configuration.

Configuration example (config.yaml)::

    gateway:
      profile_routes:
        - name: my-server
          platform: discord
          guild_id: "GUILD_ID"
          profile: server-default
        - name: trader-channel
          platform: discord
          chat_id: "CHANNEL_ID"
          profile: trader
        - name: specific-thread
          platform: discord
          chat_id: "CHANNEL_ID"
          thread_id: "THREAD_ID"
          profile: analyst

Matching priority (most specific first):
  1. platform + chat_id + thread_id  (exact thread route)
  2. platform + chat_id             (channel route)
  3. platform + guild_id            (server/guild route)
  4. platform                       (platform-wide default)
  5. No match → use default "main" profile
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

from .session import SessionSource
from .config import Platform

logger = logging.getLogger(__name__)


@dataclass
class ProfileRoute:
    """A single routing rule that maps a message source to a Hermes profile."""

    name: str
    platform: Platform
    profile: str
    enabled: bool = True

    # Matching criteria (all optional — more specific = higher priority)
    guild_id: Optional[str] = None
    chat_id: Optional[str] = None
    thread_id: Optional[str] = None
    user_id: Optional[str] = None

    model: Optional[str] = None
    provider: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict) -> "ProfileRoute":
        platform_str = data.get("platform", "")
        try:
            platform = Platform(platform_str)
        except ValueError:
            logger.warning("ProfileRoute '%s': unknown platform '%s', skipping", data.get("name", "?"), platform_str)
            raise

        return cls(
            name=data.get("name", "unnamed"),
            platform=platform,
            profile=data["profile"],
            enabled=data.get("enabled", True),
            guild_id=data.get("guild_id"),
            chat_id=data.get("chat_id"),
            thread_id=data.get("thread_id"),
            user_id=data.get("user_id"),
            model=data.get("model"),
            provider=data.get("provider"),
        )

    @property
    def specificity(self) -> int:
        score = 0
        if self.thread_id:
            score += 8
        if self.chat_id:
            score += 4
        if self.guild_id:
            score += 2
        if self.user_id:
            score += 1
        return score


def parse_profile_routes(raw: List[Dict]) -> List[ProfileRoute]:
    routes: List[ProfileRoute] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        if not entry.get("profile"):
            logger.warning("ProfileRoute missing 'profile' field, skipping: %s", entry.get("name", "?"))
            continue
        try:
            route = ProfileRoute.from_dict(entry)
            if route.enabled:
                if route.thread_id and not route.chat_id:
                    logger.warning("ProfileRoute '%s': thread_id set without chat_id, "
                                   "this may match across channels", route.name)
                routes.append(route)
        except (ValueError, KeyError):
            continue

    routes.sort(key=lambda r: r.specificity, reverse=True)
    return routes


def match_profile_route(
    source: SessionSource,
    routes: List[ProfileRoute],
) -> Optional[ProfileRoute]:
    for route in routes:
        if route.platform != source.platform:
            continue
        if route.thread_id:
            if source.thread_id != route.thread_id:
                continue
            if route.chat_id and source.chat_id != route.chat_id:
                continue
            if route.guild_id and source.guild_id != route.guild_id:
                continue
            return route
        if route.chat_id:
            if source.chat_id != route.chat_id and source.parent_chat_id != route.chat_id:
                continue
            if route.guild_id and source.guild_id != route.guild_id:
                continue
            return route
        if route.guild_id:
            if source.guild_id != route.guild_id:
                continue
            return route
        if route.user_id:
            if source.user_id != route.user_id:
                continue
            return route
        return route

    return None
