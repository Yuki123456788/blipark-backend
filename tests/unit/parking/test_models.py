from django.contrib.gis.db.models import GeometryField, LineStringField, PointField
from django.test import SimpleTestCase

from parking.models import (
    EntityKind,
    ParkingEntity,
    ParkingEntrance,
    ParkingLot,
    ParkingSegment,
    ParkingSpot,
    SourceReference,
)


class ParkingModelContractTest(SimpleTestCase):
    def test_every_domain_model_inherits_the_uuid_identity_root(self):
        assert ParkingEntity._meta.get_field("id").get_internal_type() == "UUIDField"
        for model in (ParkingLot, ParkingEntrance, ParkingSegment, ParkingSpot):
            assert issubclass(model, ParkingEntity)

    def test_entity_discriminators_match_concrete_models(self):
        assert ParkingLot.ENTITY_KIND == EntityKind.LOT
        assert ParkingEntrance.ENTITY_KIND == EntityKind.ENTRANCE
        assert ParkingSegment.ENTITY_KIND == EntityKind.SEGMENT
        assert ParkingSpot.ENTITY_KIND == EntityKind.SPOT

    def test_geometries_use_wgs84_and_preserve_source_precision(self):
        expected_fields = [
            (ParkingLot, "location", PointField),
            (ParkingLot, "boundary", GeometryField),
            (ParkingEntrance, "location", PointField),
            (ParkingSegment, "representative_point", PointField),
            (ParkingSegment, "geometry", LineStringField),
            (ParkingSpot, "location", PointField),
            (ParkingSpot, "footprint", GeometryField),
        ]

        for model, field_name, field_type in expected_fields:
            field = model._meta.get_field(field_name)
            assert isinstance(field, field_type)
            assert field.srid == 4326

    def test_source_identity_is_scoped_by_dataset(self):
        constraint_names = {constraint.name for constraint in SourceReference._meta.constraints}

        assert constraint_names == {
            "source_ref_identity_uniq",
            "source_ref_entity_dataset_uniq",
        }

    def test_spot_parent_shape_is_database_constrained(self):
        constraint_names = {constraint.name for constraint in ParkingSpot._meta.constraints}

        assert "spot_context_parent_ck" in constraint_names
