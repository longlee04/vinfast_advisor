"""Exact CAR/MOTORBIKE policy resolution against disposable PostgreSQL."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.document.application.errors import PolicyVehicleResolutionError
from src.document.domain.policy_scopes import BatteryChemistry, PolicyVehicleType
from src.document.infrastructure.policy_vehicle_resolver import SqlAlchemyPolicyVehicleResolver


@pytest.mark.asyncio
async def test_resolver_supports_exact_car_and_reviewed_motorbike_chemistry_groups(
    document_engine: AsyncEngine,
) -> None:
    now = datetime(2026, 8, 31, tzinfo=UTC)
    vehicles = (
        ("00000000-0000-0000-0000-000000008101", "CAR", "Policy Car", "policy-car", None),
        ("00000000-0000-0000-0000-000000008102", "ELECTRIC_MOTORBIKE", "Policy LFP", "policy-lfp", "LFP"),
        (
            "00000000-0000-0000-0000-000000008103",
            "ELECTRIC_MOTORBIKE",
            "Policy Lithium",
            "policy-lithium",
            "Lithium-ion",
        ),
        (
            "00000000-0000-0000-0000-000000008104",
            "ELECTRIC_MOTORBIKE",
            "Policy Unknown Battery",
            "policy-unknown-battery",
            None,
        ),
    )
    async with document_engine.begin() as connection:
        for vehicle_id, vehicle_type, model_name, slug, battery_type in vehicles:
            await connection.execute(
                text(
                    """
                    INSERT INTO vehicles (
                        vehicle_id, vehicle_type, brand, model_name, status, slug,
                        created_at, updated_at
                    ) VALUES (:id, :type, 'VinFast', :model, 'ACTIVE', :slug, :now, :now)
                    ON CONFLICT (vehicle_id) DO NOTHING
                    """
                ),
                {
                    "id": vehicle_id,
                    "type": vehicle_type,
                    "model": model_name,
                    "slug": slug,
                    "now": now,
                },
            )
            if vehicle_type == "ELECTRIC_MOTORBIKE":
                await connection.execute(
                    text(
                        """
                        INSERT INTO motorbikes (
                            vehicle_id, battery_type, created_at, updated_at
                        ) VALUES (:id, :battery_type, :now, :now)
                        ON CONFLICT (vehicle_id) DO NOTHING
                        """
                    ),
                    {"id": vehicle_id, "battery_type": battery_type, "now": now},
                )
        for vehicle_id, variant_name, slug in (
            ("00000000-0000-0000-0000-000000008105", "Plus", "policy-variant-plus"),
            ("00000000-0000-0000-0000-000000008106", "Eco", "policy-variant-eco"),
        ):
            await connection.execute(
                text(
                    """
                    INSERT INTO vehicles (
                        vehicle_id, vehicle_type, brand, model_name, variant_name, status, slug,
                        created_at, updated_at
                    ) VALUES (
                        :id, 'CAR', 'VinFast', 'Policy Variant', :variant, 'ACTIVE', :slug,
                        :now, :now
                    )
                    ON CONFLICT (vehicle_id) DO NOTHING
                    """
                ),
                {
                    "id": vehicle_id,
                    "variant": variant_name,
                    "slug": slug,
                    "now": now,
                },
            )

    factory = async_sessionmaker(document_engine, expire_on_commit=False, class_=AsyncSession)
    resolver = SqlAlchemyPolicyVehicleResolver(factory)

    car = await resolver.resolve_vehicle_ids(
        ("Policy Car",), vehicle_type=PolicyVehicleType.CAR
    )
    lfp_group = await resolver.resolve_vehicle_ids(
        ("MOTORBIKE_LFP",),
        vehicle_type=PolicyVehicleType.MOTORBIKE,
        battery_chemistry=BatteryChemistry.LFP,
    )
    non_lfp_group = await resolver.resolve_vehicle_ids(
        ("MOTORBIKE_NON_LFP",), vehicle_type=PolicyVehicleType.MOTORBIKE
    )

    assert car == (vehicles[0][0],)
    assert lfp_group == (vehicles[1][0],)
    assert non_lfp_group == (vehicles[2][0],)
    assert await resolver.resolve_vehicle_ids(
        ("Policy Variant Plus",), vehicle_type=PolicyVehicleType.CAR
    ) == ("00000000-0000-0000-0000-000000008105",)
    with pytest.raises(PolicyVehicleResolutionError):
        await resolver.resolve_vehicle_ids(
            ("Policy Variant",), vehicle_type=PolicyVehicleType.CAR
        )
    with pytest.raises(PolicyVehicleResolutionError):
        await resolver.resolve_vehicle_ids(
            ("Policy Unknown Battery",),
            vehicle_type=PolicyVehicleType.MOTORBIKE,
            battery_chemistry=BatteryChemistry.LFP,
        )
