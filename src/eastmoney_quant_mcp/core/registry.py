"""Small extension registries for future providers and research features."""

from collections.abc import Callable

PROVIDER_REGISTRY: dict[str, object] = {}
FEATURE_REGISTRY: dict[str, Callable] = {}


def register_provider(name: str):
    def decorator(provider):
        if name in PROVIDER_REGISTRY:
            raise ValueError(f"provider already registered: {name}")
        PROVIDER_REGISTRY[name] = provider
        return provider
    return decorator


def register_feature(name: str):
    def decorator(feature: Callable):
        if name in FEATURE_REGISTRY:
            raise ValueError(f"feature already registered: {name}")
        FEATURE_REGISTRY[name] = feature
        return feature
    return decorator
