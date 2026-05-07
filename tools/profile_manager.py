"""
Profile and route management tool for Hermes Agent.

Allows the agent to create profiles, add/remove routing rules,
and list current configuration — all via natural language requests.

Hot-reloads routes without gateway restart by invalidating the cache.
"""

import json
import logging
import os
import re
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.registry import registry

logger = logging.getLogger(__name__)

_HERMES_HOME = Path(os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes")))
_PROFILES_DIR = _HERMES_HOME / "profiles"
_CONFIG_PATH = _HERMES_HOME / "config.yaml"


def _read_config() -> dict:
    if not _CONFIG_PATH.exists():
        return {}
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _write_config(config: dict) -> None:
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _invalidate_route_cache() -> None:
    """Invalidate the gateway's profile routes cache so next message reloads."""
    try:
        from gateway.run import _gateway_runner_ref
        runner = _gateway_runner_ref()
        if runner is not None:
            runner._profile_routes_cache = None
            logger.info("Profile routes cache invalidated for hot-reload")
    except Exception as e:
        logger.warning("Could not invalidate route cache: %s", e)


def profile_create(
    name: str,
    personality: str,
    model: Optional[str] = None,
    provider: Optional[str] = None,
) -> str:
    """Create a new profile directory and config.yaml."""
    if not name or not re.match(r'^[a-zA-Z0-9_-]+$', name):
        return f"Error: Invalid profile name '{name}'. Use alphanumeric, hyphens, underscores only."

    profile_dir = _PROFILES_DIR / name
    if profile_dir.exists():
        return f"Error: Profile '{name}' already exists at {profile_dir}"

    profile_dir.mkdir(parents=True, exist_ok=True)

    config = {"personality": personality}
    if model or provider:
        config["model"] = {}
        if model:
            config["model"]["default"] = model
        if provider:
            config["model"]["provider"] = provider

    config_path = profile_dir / "config.yaml"
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    return f"Profile '{name}' created at {config_path}"


def profile_update(
    name: str,
    personality: Optional[str] = None,
    model: Optional[str] = None,
    provider: Optional[str] = None,
) -> str:
    """Update an existing profile's config."""
    profile_dir = _PROFILES_DIR / name
    config_path = profile_dir / "config.yaml"

    if not config_path.exists():
        return f"Error: Profile '{name}' not found"

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    if personality:
        config["personality"] = personality
    if model or provider:
        if "model" not in config:
            config["model"] = {}
        if model:
            config["model"]["default"] = model
        if provider:
            config["model"]["provider"] = provider

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    return f"Profile '{name}' updated"


def profile_remove(name: str) -> str:
    """Remove a profile directory."""
    import shutil
    profile_dir = _PROFILES_DIR / name
    if not profile_dir.exists():
        return f"Error: Profile '{name}' not found"

    shutil.rmtree(profile_dir)
    return f"Profile '{name}' removed"


def profile_list() -> str:
    """List all available profiles."""
    if not _PROFILES_DIR.exists():
        return "No profiles directory found."

    profiles = []
    for d in sorted(_PROFILES_DIR.iterdir()):
        if d.is_dir() and (d / "config.yaml").exists():
            with open(d / "config.yaml", "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            personality = cfg.get("personality", "(no personality set)")[:80]
            model = cfg.get("model", {}).get("default", "(default)")
            profiles.append(f"  {d.name}: model={model}, personality=\"{personality}\"")

    if not profiles:
        return "No profiles found."
    return "Available profiles:\n" + "\n".join(profiles)


def route_add(
    name: str,
    platform: str,
    chat_id: str,
    profile: str,
    enabled: bool = True,
) -> str:
    """Add a profile route to config.yaml and hot-reload."""
    # Verify profile exists
    if not (_PROFILES_DIR / profile / "config.yaml").exists():
        return f"Error: Profile '{profile}' not found. Create it first with action='create_profile'."

    config = _read_config()

    routes = config.get("profile_routes", [])
    # Check for duplicate name
    for r in routes:
        if r.get("name") == name:
            return f"Error: Route '{name}' already exists. Use action='update_route' to modify it."

    new_route = {
        "name": name,
        "platform": platform,
        "chat_id": str(chat_id),
        "profile": profile,
        "enabled": enabled,
    }
    routes.append(new_route)
    config["profile_routes"] = routes
    _write_config(config)

    _invalidate_route_cache()

    return f"Route '{name}' added: {platform} channel {chat_id} → profile '{profile}' (hot-reloaded)"


def route_remove(name: str) -> str:
    """Remove a profile route from config.yaml and hot-reload."""
    config = _read_config()
    routes = config.get("profile_routes", [])

    new_routes = [r for r in routes if r.get("name") != name]
    if len(new_routes) == len(routes):
        return f"Error: Route '{name}' not found."

    config["profile_routes"] = new_routes
    _write_config(config)

    _invalidate_route_cache()

    return f"Route '{name}' removed (hot-reloaded)"


def route_list() -> str:
    """List current profile routes."""
    config = _read_config()
    routes = config.get("profile_routes", [])

    if not routes:
        return "No profile routes configured."

    lines = []
    for r in routes:
        status = "enabled" if r.get("enabled", True) else "disabled"
        lines.append(
            f"  {r['name']}: {r['platform']} chat_id={r.get('chat_id', '?')} → profile='{r['profile']}' ({status})"
        )
    return "Current routes:\n" + "\n".join(lines)


def profile_manager(
    action: str,
    name: Optional[str] = None,
    personality: Optional[str] = None,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    platform: Optional[str] = None,
    chat_id: Optional[str] = None,
    profile: Optional[str] = None,
    enabled: bool = True,
    **kwargs,
) -> str:
    """Dispatch profile management actions."""

    if action == "create_profile":
        if not name or not personality:
            return "Error: 'name' and 'personality' required for create_profile"
        return profile_create(name, personality, model, provider)

    elif action == "update_profile":
        if not name:
            return "Error: 'name' required for update_profile"
        return profile_update(name, personality, model, provider)

    elif action == "remove_profile":
        if not name:
            return "Error: 'name' required for remove_profile"
        return profile_remove(name)

    elif action == "list_profiles":
        return profile_list()

    elif action == "add_route":
        if not name or not platform or not chat_id or not profile:
            return "Error: 'name', 'platform', 'chat_id', 'profile' required for add_route"
        return route_add(name, platform, chat_id, profile, enabled)

    elif action == "remove_route":
        if not name:
            return "Error: 'name' required for remove_route"
        return route_remove(name)

    elif action == "list_routes":
        return route_list()

    else:
        return f"Unknown action '{action}'. Use: create_profile, update_profile, remove_profile, list_profiles, add_route, remove_route, list_routes"


PROFILE_MANAGER_SCHEMA = {
    "name": "profile_manager",
    "description": """Manage profiles and channel routing for this gateway.

Use action='create_profile' to create a new profile with a personality, model, and provider.
Use action='add_route' to route a specific channel/thread to a profile (hot-reloads without restart).
Use action='list_profiles' or 'list_routes' to inspect current config.
Use action='update_profile' to change a profile's personality or model.
Use action='remove_route' or 'remove_profile' to delete entries.

When a user says "make a profile for this channel" or similar, infer the platform and chat_id
from the current conversation context (HERMES_SESSION_PLATFORM, HERMES_SESSION_CHAT_ID env vars).""",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "One of: create_profile, update_profile, remove_profile, list_profiles, add_route, remove_route, list_routes",
            },
            "name": {
                "type": "string",
                "description": "Profile name or route name",
            },
            "personality": {
                "type": "string",
                "description": "System prompt / personality for the profile",
            },
            "model": {
                "type": "string",
                "description": "Default model for the profile (e.g. 'glm-5-turbo', 'gpt-4o')",
            },
            "provider": {
                "type": "string",
                "description": "Provider for the profile (e.g. 'zai', 'openai')",
            },
            "platform": {
                "type": "string",
                "description": "Platform for routing (e.g. 'discord', 'telegram')",
            },
            "chat_id": {
                "type": "string",
                "description": "Channel/chat ID to route",
            },
            "profile": {
                "type": "string",
                "description": "Profile name to route to (for add_route)",
            },
            "enabled": {
                "type": "boolean",
                "description": "Whether the route is enabled (default true)",
            },
        },
        "required": ["action"],
    },
}


registry.register(
    name="profile_manager",
    toolset="hermes-cli",
    schema=PROFILE_MANAGER_SCHEMA,
    handler=lambda args, **kw: profile_manager(
        action=args.get("action", ""),
        name=args.get("name"),
        personality=args.get("personality"),
        model=args.get("model"),
        provider=args.get("provider"),
        platform=args.get("platform"),
        chat_id=args.get("chat_id"),
        profile=args.get("profile"),
        enabled=args.get("enabled", True),
    ),
    emoji="🔀",
)
