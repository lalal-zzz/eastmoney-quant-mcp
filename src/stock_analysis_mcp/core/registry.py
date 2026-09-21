"""
Extension registries for future provider abstraction and feature plugins.

Reserved for future use:
- PROVIDER_REGISTRY: route data requests through registered providers
  (e.g., "eastmoney", "tushare", custom adapters) instead of direct API calls.
- FEATURE_REGISTRY: register pluggable research features (indicators, screeners)
  that can be dynamically enabled/disabled.

Currently unused — all data sources are hard-coded in data/providers/ and data/sources.py.
When a multi-provider abstraction is needed, use @register_provider / @register_feature
decorators to populate these registries.
"""

from collections.abc import Callable

# Reserved: future multi-provider routing
PROVIDER_REGISTRY: dict[str, object] = {}

# Reserved: future pluggable feature system
FEATURE_REGISTRY: dict[str, Callable] = {}


def register_provider(name: str):
    """Decorator to register a data provider under the given name."""
    def decorator(provider):
        if name in PROVIDER_REGISTRY:
            raise ValueError(f"provider already registered: {name}")
        PROVIDER_REGISTRY[name] = provider
        return provider
    return decorator


def register_feature(name: str):
    """Decorator to register a research feature under the given name."""
    def decorator(feature: Callable):
        if name in FEATURE_REGISTRY:
            raise ValueError(f"feature already registered: {name}")
        FEATURE_REGISTRY[name] = feature
        return feature
    return decorator
