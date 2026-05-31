"""Profile-based routing for the gateway with hierarchical matching.

Allows a single Hermes instance to route specific Discord guilds/channels/threads
to different profiles — each with their own model, tools, memory, and persona.

Matching priority (most specific first):
  1. platform + chat_id + thread_id (exact thread)  — specificity 8
  2. platform + chat_id (channel route)             — specificity 4
  3. platform + guild_id (guild/server route)       — specificity 2
  4. No match                                       → default profile

Hierarchical matching:
For Discord forum channels, checks the full parent chain:
- Forum channel → Forum post → Comment
- Matches if any level of the hierarchy matches a configured route

Configuration (config.yaml):

    gateway:
      profile_routes:
        - name: server-default
          platform: discord
          guild_id: "YOUR_GUILD_ID"
          profile: server-profile

        - name: special-channel
          platform: discord
          guild_id: "YOUR_GUILD_ID"
          chat_id: "YOUR_CHANNEL_ID"
          profile: channel-profile

        - name: thread-route
          platform: discord
          chat_id: "YOUR_CHANNEL_ID"
          thread_id: "YOUR_THREAD_ID"
          profile: thread-profile
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

import logging

logger = logging.getLogger(__name__)


# Simple cache for forum post → channel mappings
# In production, this should be persisted to a database
_forum_post_cache: Dict[str, str] = {}  # post_id → channel_id


def register_forum_post(post_id: str, channel_id: str) -> None:
    """Register a forum post's parent channel for hierarchical matching."""
    _forum_post_cache[post_id] = channel_id
    logger.debug("Registered forum post %s → channel %s", post_id, channel_id)


def resolve_forum_channel(post_id: str) -> Optional[str]:
    """Get the parent channel ID for a forum post, if cached."""
    return _forum_post_cache.get(post_id)


@dataclass(frozen=True)
class ProfileRoute:
    """A single routing rule that maps a platform scope to a profile."""

    name: str
    platform: str
    profile: str
    guild_id: Optional[str] = None
    chat_id: Optional[str] = None
    thread_id: Optional[str] = None
    enabled: bool = True

    @property
    def specificity(self) -> int:
        """Higher value = more specific match."""
        s = 0
        if self.guild_id:
            s += 2
        if self.chat_id:
            s += 4
        if self.thread_id:
            s += 8
        return s

    def matches(
        self,
        platform: str,
        guild_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        parent_chat_id: Optional[str] = None,
    ) -> bool:
        """Return True if this route matches the given source fields.
        
        Supports hierarchical matching for Discord forums:
        - Direct channel match: chat_id == route.chat_id
        - Thread in channel: parent_chat_id == route.chat_id
        - Forum post: parent_chat_id is the forum post, check if post belongs to route's channel
        - Comment on forum post: parent_chat_id is the forum post, check hierarchy
        """
        if not self.enabled:
            return False
        if self.platform != platform:
            return False
        if self.thread_id and self.thread_id != thread_id:
            return False
        
        # Hierarchical chat_id matching
        if self.chat_id:
            # Direct match
            if self.chat_id == chat_id:
                return True
            # Parent match (thread or direct child)
            if self.chat_id == parent_chat_id:
                return True
            # Forum post hierarchy: check if parent_chat_id is a forum post
            # that belongs to this channel
            if parent_chat_id:
                parent_channel = resolve_forum_channel(parent_chat_id)
                if parent_channel and self.chat_id == parent_channel:
                    return True
        
        if self.guild_id and self.guild_id != guild_id:
            return False
        return True


def parse_profile_routes(raw: Optional[List[Dict[str, Any]]]) -> List[ProfileRoute]:
    """Parse profile_routes from config.yaml into ProfileRoute objects.

    Returns routes sorted by specificity (most specific first).
    """
    if not raw:
        return []
    routes: List[ProfileRoute] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name", "")
        platform = entry.get("platform", "")
        profile = entry.get("profile", "")
        if not platform or not profile:
            logger.warning(
                "Skipping profile route %s: missing platform or profile",
                name,
            )
            continue
        routes.append(
            ProfileRoute(
                name=name,
                platform=platform,
                profile=profile,
                guild_id=entry.get("guild_id"),
                chat_id=entry.get("chat_id"),
                thread_id=entry.get("thread_id"),
                enabled=entry.get("enabled", True),
            )
        )
    # Sort: most specific first so the first match wins.
    routes.sort(key=lambda r: r.specificity, reverse=True)
    logger.debug("Loaded %d profile routes (most-specific-first)", len(routes))
    return routes


def match_profile_route(
    routes: List[ProfileRoute],
    platform: str,
    guild_id: Optional[str] = None,
    chat_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    parent_chat_id: Optional[str] = None,
) -> Optional[ProfileRoute]:
    """Return the best-matching route, or None for no match."""
    for route in routes:
        if route.matches(platform, guild_id=guild_id, chat_id=chat_id, thread_id=thread_id, parent_chat_id=parent_chat_id):
            return route
    return None
