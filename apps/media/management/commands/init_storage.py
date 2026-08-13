"""Create the object-storage bucket if it is missing.

    docker compose run --rm web python manage.py init_storage

Development points ``default_storage`` at the MinIO container, and MinIO
starts with no buckets at all — so without this the first upload fails with
``NoSuchBucket`` and nothing in the interface explains why.

Safe to run repeatedly, and it never touches an existing bucket's contents
or its policy. In production the bucket is created by whoever provisions the
account, and RFP §4.4 requires it to be **private**; this command does not
make it public and refuses to guess a policy.
"""

from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create the media bucket if it does not exist (development)"

    def handle(self, *args, **options):
        bucket = getattr(default_storage, "bucket_name", None)
        if bucket is None:
            raise CommandError(
                "The configured storage backend has no bucket — nothing to do. "
                "This command is for the S3-compatible backend only."
            )

        connection = default_storage.connection
        client = connection.meta.client

        existing = {
            entry["Name"] for entry in client.list_buckets().get("Buckets", [])
        }
        if bucket in existing:
            self.stdout.write(f"Bucket '{bucket}' already exists.")
            return

        client.create_bucket(Bucket=bucket)
        self.stdout.write(self.style.SUCCESS(f"Created bucket '{bucket}'."))
        self.stdout.write(
            "It is private by default. Keep it that way — RFP §4.4, §21.10: "
            "files are reached only through /media/<uuid>/<variant>/."
        )
