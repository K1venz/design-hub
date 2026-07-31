from decimal import Decimal

from design_hub.composition import build_mock_registry


def test_mock_registry_is_explicit_and_has_no_4k_model_alias() -> None:
    registry = build_mock_registry({"gpt-image-2": Decimal("0.40")})

    assert registry.get("gpt-image-2").unit_cost == Decimal("0.40")
    assert "gpt-image-2-4k" not in registry
