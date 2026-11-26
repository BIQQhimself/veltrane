from __future__ import annotations

from app.providers.ccxt_provider import build_providers
from app.providers.deriv import build_deriv_provider
from app.providers.paper import PaperProvider


def provider_registry() -> dict:
    registry: dict = build_providers()
    deriv = build_deriv_provider()
    registry[deriv.info.key] = deriv
    paper = PaperProvider()
    registry[paper.info.key] = paper
    return registry


def get_provider(key: str):
    registry = provider_registry()
    if key not in registry:
        from app.core.errors import not_found

        raise not_found("provider_not_found", f"Unknown provider '{key}'.")
    return registry[key]


def provider_catalog() -> list[dict]:
    out = []
    for key, adapter in sorted(provider_registry().items()):
        out.append(
            {
                "key": key,
                "name": adapter.info.name,
                "kind": adapter.info.kind,
                "asset_classes": adapter.info.asset_classes,
                "requires_passphrase": adapter.info.requires_passphrase,
                "requires_api_secret": adapter.info.requires_api_secret,
                "requires_app_id": adapter.info.requires_app_id,
                "token_label": adapter.info.token_label,
                "supports_oauth": adapter.info.supports_oauth,
                "auth_style": adapter.info.auth_style,
                "docs_url": adapter.info.docs_url,
                "status": adapter.info.status,
                "notes": adapter.info.notes,
                "capabilities": adapter.capabilities.as_dict(),
            }
        )
    return out
