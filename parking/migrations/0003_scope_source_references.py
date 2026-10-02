import hashlib
import json

from django.db import migrations, models


def scope_existing_spot_references(apps, schema_editor):
    ParkingSpot = apps.get_model("parking", "ParkingSpot")
    SourceReference = apps.get_model("parking", "SourceReference")

    references = SourceReference.objects.filter(
        dataset__in=("off_street_spot", "on_street_spot")
    ).iterator()
    for reference in references:
        spot = ParkingSpot.objects.filter(pk=reference.entity_id).first()
        if spot is None:
            continue

        if reference.dataset == "off_street_spot":
            parent_id = spot.lot_id
            parent_dataset = "car_park"
            payload = (
                spot.source_space_type,
                spot.has_charging_point,
                spot.floor,
                spot.length_cm,
                spot.width_cm,
            )
            canonical = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
            discriminator = f"attrs:{hashlib.sha256(canonical.encode()).hexdigest()[:32]}"
        else:
            parent_id = spot.segment_id
            parent_dataset = "parking_segment"
            discriminator = (
                f"position:{spot.location.x:.7f}:{spot.location.y:.7f}"
                if spot.location is not None
                else ""
            )

        parent_reference = SourceReference.objects.filter(
            entity_id=parent_id,
            source=reference.source,
            authority_code=reference.authority_code,
            dataset=parent_dataset,
        ).first()
        reference.source_scope = parent_reference.source_id if parent_reference else ""
        reference.source_discriminator = discriminator
        reference.save(update_fields=("source_scope", "source_discriminator"))


class Migration(migrations.Migration):
    dependencies = [("parking", "0002_add_sync_observability")]

    operations = [
        migrations.AddField(
            model_name="sourcereference",
            name="source_scope",
            field=models.CharField(blank=True, default="", max_length=255),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="sourcereference",
            name="source_discriminator",
            field=models.CharField(blank=True, default="", max_length=255),
            preserve_default=False,
        ),
        migrations.RunPython(scope_existing_spot_references, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="sourcereference",
            name="source_ref_identity_uniq",
        ),
        migrations.AddConstraint(
            model_name="sourcereference",
            constraint=models.UniqueConstraint(
                fields=(
                    "source",
                    "authority_code",
                    "dataset",
                    "source_scope",
                    "source_id",
                    "source_discriminator",
                ),
                name="source_ref_identity_uniq",
            ),
        ),
    ]
