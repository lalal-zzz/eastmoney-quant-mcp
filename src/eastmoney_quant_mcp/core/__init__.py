"""Stable application primitives shared by MCP, CLI and future extensions."""

from .config import Settings, get_settings
from .registry import FEATURE_REGISTRY, PROVIDER_REGISTRY, register_feature, register_provider

__all__ = ["Settings", "get_settings", "FEATURE_REGISTRY", "PROVIDER_REGISTRY", "register_feature", "register_provider"]
