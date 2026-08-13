"""Uploads and file access — RFP §4.4, §15, §684, §21.10. Spec section 7.

The §21 tests here are about a *file*, not a page: RFP §21.10 is the claim
that a child's photo cannot be fetched by anyone who is not entitled to see
that child, whatever URL they construct.
"""

import io

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from apps.core.models import AuditAction, AuditLog
from apps.media import services
from apps.media.models import MediaFile, ObservationMedia
from apps.observations.models import ObservationType
from apps.observations.services import create_observation

pytestmark = pytest.mark.django_db

PASSWORD = "test-password-1234"


def login(client, user):
    assert client.login(username=user.username, password=PASSWORD)
    return client


def make_jpeg(*, size=(60, 40), with_gps=True) -> SimpleUploadedFile:
    """A real JPEG, with GPS coordinates in its EXIF when asked.

    Written rather than committed as a fixture file so the coordinates are
    visible in the test that cares about them.
    """
    import piexif

    image = Image.new("RGB", size, (120, 160, 200))
    buffer = io.BytesIO()

    if with_gps:
        gps = {
            piexif.GPSIFD.GPSLatitudeRef: b"N",
            piexif.GPSIFD.GPSLatitude: ((47, 1), (55, 1), (0, 1)),
            piexif.GPSIFD.GPSLongitudeRef: b"E",
            piexif.GPSIFD.GPSLongitude: ((106, 1), (55, 1), (0, 1)),
        }
        exif = piexif.dump({"0th": {}, "Exif": {}, "GPS": gps,
                            "1st": {}, "thumbnail": None})
        image.save(buffer, format="JPEG", exif=exif)
    else:
        image.save(buffer, format="JPEG")

    return SimpleUploadedFile("Батаа_гэрийн_зураг.jpg", buffer.getvalue(),
                              content_type="image/jpeg")


def make_png() -> SimpleUploadedFile:
    image = Image.new("RGBA", (30, 30), (10, 200, 90, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return SimpleUploadedFile("зураг.png", buffer.getvalue(),
                              content_type="image/png")


@pytest.fixture
def photo(world):
    return services.set_child_photo(actor=world["dulmaa"],
                                    child=world["bataa"],
                                    upload=make_jpeg())


def serve_url(media, variant="full"):
    return reverse("media:serve", args=[media.public_id, variant])


# ------------------------------------------------------------------ §21.10
# CLAUDE.md §4.1, through the HTTP client. A file is not reachable by URL.

def test_teacher_from_another_group_gets_404(client, world, photo,
                                             make_teacher, make_group):
    other = make_group(world["naran"], world["naran_year"], "Сарнай")
    stranger = make_teacher(world["naran"], other, username="stranger")
    login(client, stranger)

    assert client.get(serve_url(photo)).status_code == 404


def test_guardian_of_another_child_gets_404(client, world, photo,
                                            make_guardian, make_child):
    elsewhere = make_child(world["naran"], world["sunflower"],
                           first_name="Өөр")
    outsider = make_guardian(elsewhere, world["naran"], username="other_mother")
    login(client, outsider)

    assert client.get(serve_url(photo)).status_code == 404


def test_user_from_another_kindergarten_gets_404(client, world, photo):
    login(client, world["oyun"])

    assert client.get(serve_url(photo)).status_code == 404


def test_an_anonymous_request_is_redirected_to_login(client, world, photo):
    response = client.get(serve_url(photo))

    assert response.status_code == 302
    assert reverse("accounts:login") in response["Location"]


def test_a_relative_storage_url_is_never_redirected_to(world, photo,
                                                       monkeypatch):
    """RFP §21.10 — only an off-site signed link short-circuits the stream.

    A local backend answers ``url()`` with a path rather than raising. If
    ``MEDIA_URL`` were ever set, redirecting there would serve the file with
    no permission check at all.
    """
    monkeypatch.setattr(default_storage, "url",
                        lambda key: "/media-root/leak.jpg")

    assert services.file_url(photo) is None


def test_an_unknown_id_gets_404_not_a_different_answer(client, world):
    """Same 404 as "not yours", so an id cannot be probed for existence."""
    import uuid

    login(client, world["dulmaa"])
    url = reverse("media:serve", args=[uuid.uuid4(), "full"])

    assert client.get(url).status_code == 404


def test_an_unknown_variant_gets_404(client, world, photo):
    login(client, world["dulmaa"])

    assert client.get(serve_url(photo, "original")).status_code == 404


def test_the_entitled_teacher_gets_the_file(client, world, photo):
    login(client, world["dulmaa"])

    response = client.get(serve_url(photo))

    assert response.status_code == 200
    assert response["Content-Type"] == "image/jpeg"


def test_the_guardian_gets_their_own_childs_photo(client, world, photo):
    login(client, world["bataa_mother"])

    assert client.get(serve_url(photo)).status_code == 200


def test_the_previous_kindergarten_cannot_fetch_the_new_ones_file(client,
                                                                  world):
    """A file follows the same rule as the records — CLAUDE.md §1.2."""
    from apps.children.models import Enrollment

    Enrollment.objects.filter(child=world["bataa"]).update(
        status=Enrollment.Status.TRANSFERRED
    )
    Enrollment.objects.create(
        kindergarten=world["och"], child=world["bataa"], group=world["petal"],
        school_year=world["och_year"], started_on=__import__("datetime").date(2026, 1, 16),
    )
    world["bataa"].kindergarten = world["och"]
    world["bataa"].save()

    theirs = services.set_child_photo(actor=world["oyun"],
                                      child=world["bataa"],
                                      upload=make_jpeg())
    assert theirs.kindergarten_id == world["och"].pk

    login(client, world["dulmaa"])
    assert client.get(serve_url(theirs)).status_code == 404

    login(client, world["bataa_mother"])
    assert client.get(serve_url(theirs)).status_code == 200


# ------------------------------------------------------------------ §684, §15

def test_the_mime_type_is_read_from_the_content(world):
    """CLAUDE.md §1.6 — a .jpg can be anything at all."""
    disguised = SimpleUploadedFile(
        "photo.jpg", b"#!/bin/sh\nrm -rf /\n", content_type="image/jpeg"
    )

    with pytest.raises(ValidationError):
        services.set_child_photo(actor=world["dulmaa"], child=world["bataa"],
                                 upload=disguised)

    assert not MediaFile.objects.exists()


def test_a_pdf_named_jpg_is_rejected(world):
    pdf = SimpleUploadedFile("scan.jpg", b"%PDF-1.4\n%\xc3\xa4\n",
                             content_type="image/jpeg")

    with pytest.raises(ValidationError):
        services.set_child_photo(actor=world["dulmaa"], child=world["bataa"],
                                 upload=pdf)


def test_heic_is_refused_with_an_explanation(world, monkeypatch):
    """Spec section 7 — the conversion is Phase 2, so say so in Mongolian."""
    monkeypatch.setattr(services, "_detect_mime", lambda payload: "image/heic")

    with pytest.raises(ValidationError) as caught:
        services.set_child_photo(actor=world["dulmaa"], child=world["bataa"],
                                 upload=make_jpeg())

    assert "HEIC" in " ".join(caught.value.messages)


def test_an_oversized_file_is_refused(world, settings):
    settings.MAX_UPLOAD_SIZE_MB = 0.00001

    with pytest.raises(ValidationError):
        services.set_child_photo(actor=world["dulmaa"], child=world["bataa"],
                                 upload=make_jpeg())


def test_an_empty_file_is_refused(world):
    empty = SimpleUploadedFile("empty.jpg", b"", content_type="image/jpeg")

    with pytest.raises(ValidationError):
        services.set_child_photo(actor=world["dulmaa"], child=world["bataa"],
                                 upload=empty)


def test_png_is_accepted(world):
    media = services.set_child_photo(actor=world["dulmaa"],
                                     child=world["bataa"], upload=make_png())

    assert media.mime_type == "image/png"
    assert media.width == 30


# ------------------------------------------------------------------ EXIF ★

def test_gps_coordinates_are_stripped(world):
    """Not in the RFP, mandatory anyway — spec section 7.

    A phone photo carries the coordinates of the place it was taken. For a
    photo taken at home, that is the child's home address.
    """
    import piexif

    upload = make_jpeg(with_gps=True)
    # The fixture really does carry coordinates, or this test proves nothing.
    assert piexif.load(upload.read())["GPS"]
    upload.seek(0)

    media = services.set_child_photo(actor=world["dulmaa"],
                                     child=world["bataa"], upload=upload)

    stored = default_storage.open(media.storage_key).read()
    assert piexif.load(stored)["GPS"] == {}
    assert b"GPS" not in stored


# ------------------------------------------------------------------ storage

def test_the_stored_path_reveals_nothing(world, photo):
    """RFP §4.4 — the real filename is display-only."""
    assert "Батаа" not in photo.storage_key
    assert photo.storage_key.endswith(".jpg")
    assert photo.original_name == "Батаа_гэрийн_зураг.jpg"


def test_two_uploads_do_not_collide(world):
    first = services.set_child_photo(actor=world["dulmaa"],
                                     child=world["bataa"], upload=make_jpeg())
    second = services.set_child_photo(actor=world["dulmaa"],
                                      child=world["bataa"], upload=make_jpeg())

    assert first.storage_key != second.storage_key
    assert first.public_id != second.public_id


def test_the_child_points_at_the_newest_photo(world):
    services.set_child_photo(actor=world["dulmaa"], child=world["bataa"],
                             upload=make_jpeg())
    second = services.set_child_photo(actor=world["dulmaa"],
                                      child=world["bataa"], upload=make_png())

    world["bataa"].refresh_from_db()
    assert world["bataa"].photo == second
    # The earlier one is kept: the portfolio shows the picture that was
    # current in each year.
    assert MediaFile.objects.filter(child=world["bataa"]).count() == 2


# ------------------------------------------------------------------ §5.1

def test_a_teacher_attaches_a_photo_to_an_observation(world):
    import datetime as dt

    daily = ObservationType.objects.get(kindergarten=None, code="daily")
    observation = create_observation(
        actor=world["dulmaa"], child=world["bataa"], type=daily,
        observed_on=dt.date(2025, 10, 1),
    )

    link = services.attach_to_observation(
        actor=world["dulmaa"], observation=observation, upload=make_jpeg(),
        caption="Барьсан цамхаг",
    )

    assert link.media_file.purpose == MediaFile.Purpose.OBSERVATION
    assert link.caption == "Барьсан цамхаг"
    assert link.taken_on == observation.observed_on
    assert observation.media_links.count() == 1


def test_a_guardian_cannot_attach_to_an_observation(world):
    import datetime as dt

    daily = ObservationType.objects.get(kindergarten=None, code="daily")
    observation = create_observation(
        actor=world["dulmaa"], child=world["bataa"], type=daily,
        observed_on=dt.date(2025, 10, 1),
    )

    with pytest.raises(PermissionDenied):
        services.attach_to_observation(
            actor=world["bataa_mother"], observation=observation,
            upload=make_jpeg(),
        )


def test_a_guardian_may_set_their_own_childs_photo(world):
    """RFP §2.3 lists photographs among what a family contributes."""
    media = services.set_child_photo(actor=world["bataa_mother"],
                                     child=world["bataa"], upload=make_jpeg())

    assert media.child == world["bataa"]


def test_a_stranger_cannot_upload(world):
    with pytest.raises(PermissionDenied):
        services.set_child_photo(actor=world["oyun"], child=world["bataa"],
                                 upload=make_jpeg())


# ------------------------------------------------------------------ §3.4, §971

def test_deleting_archives_the_row_and_clears_the_pointer(world, photo):
    services.delete_media(actor=world["dulmaa"], media=photo)

    assert not MediaFile.objects.filter(pk=photo.pk).exists()
    assert MediaFile.all_objects.get(pk=photo.pk).deleted_at is not None
    world["bataa"].refresh_from_db()
    assert world["bataa"].photo is None


def test_deleting_also_archives_the_observation_link(world):
    import datetime as dt

    daily = ObservationType.objects.get(kindergarten=None, code="daily")
    observation = create_observation(
        actor=world["dulmaa"], child=world["bataa"], type=daily,
        observed_on=dt.date(2025, 10, 1),
    )
    link = services.attach_to_observation(
        actor=world["dulmaa"], observation=observation, upload=make_jpeg()
    )

    services.delete_media(actor=world["dulmaa"], media=link.media_file)

    assert not ObservationMedia.objects.filter(pk=link.pk).exists()


def test_an_archived_file_is_no_longer_served(client, world, photo):
    services.delete_media(actor=world["dulmaa"], media=photo)
    login(client, world["dulmaa"])

    assert client.get(serve_url(photo)).status_code == 404


def test_uploading_writes_an_audit_row(world):
    services.set_child_photo(actor=world["dulmaa"], child=world["bataa"],
                             upload=make_jpeg())

    assert AuditLog.objects.filter(
        action=AuditAction.CREATE, actor_user=world["dulmaa"],
        object_type="media.MediaFile",
    ).exists()


def test_fetching_a_file_is_recorded(client, world, photo):
    """RFP §971 — who downloaded which child's photo."""
    login(client, world["bataa_mother"])
    client.get(serve_url(photo))

    entry = AuditLog.objects.filter(
        action=AuditAction.DOWNLOAD, actor_user=world["bataa_mother"]
    ).first()
    assert entry is not None
    assert entry.child == world["bataa"]


# ------------------------------------------------------------------ screens

def test_the_upload_screens_render_and_work(client, world):
    login(client, world["dulmaa"])
    url = reverse("media:child_photo", args=[world["bataa"].pk])

    assert client.get(url).status_code == 200

    response = client.post(url, {"photo": make_jpeg()})

    assert response.status_code == 302
    world["bataa"].refresh_from_db()
    assert world["bataa"].photo is not None


def test_the_upload_screen_refuses_another_childs_id(client, world):
    login(client, world["oyun"])

    response = client.post(
        reverse("media:child_photo", args=[world["bataa"].pk]),
        {"photo": make_jpeg()},
    )

    assert response.status_code == 404
    assert not MediaFile.objects.exists()


def test_a_rejected_upload_explains_itself(client, world):
    login(client, world["dulmaa"])

    response = client.post(
        reverse("media:child_photo", args=[world["bataa"].pk]),
        {"photo": SimpleUploadedFile("x.jpg", b"not an image",
                                     content_type="image/jpeg")},
    )

    assert response.status_code == 200
    assert "JPEG" in response.content.decode()
    assert not MediaFile.objects.exists()


# ------------------------------------------------- §21.4, the other two screens
# CLAUDE.md §4.1 for ``media:observation_attach`` and ``media:delete``. The
# services behind them are covered above through direct calls, which is not
# the same claim: a view that forgot to check would still pass every one of
# those. These go through the HTTP client.
#
# The three mandated names are already taken in this module by the §21.10
# tests for ``media:serve``, so each is prefixed with the screen it exercises.

@pytest.fixture
def observation(world):
    import datetime as dt

    daily = ObservationType.objects.get(kindergarten=None, code="daily")
    return create_observation(
        actor=world["dulmaa"], child=world["bataa"], type=daily,
        observed_on=dt.date(2025, 10, 1),
    )


def attach_url(child, observation):
    return reverse("media:observation_attach", args=[child.pk, observation.pk])


def delete_url(child, media):
    return reverse("media:delete", args=[child.pk, media.public_id])


def test_attach_teacher_from_another_group_gets_404(client, world, observation,
                                                    make_teacher, make_group):
    other = make_group(world["naran"], world["naran_year"], "Сарнай")
    stranger = make_teacher(world["naran"], other, username="stranger")
    login(client, stranger)

    url = attach_url(world["bataa"], observation)
    assert client.get(url).status_code == 404
    assert client.post(url, {"photo": make_jpeg()}).status_code == 404
    assert observation.media_links.count() == 0


def test_attach_guardian_of_another_child_gets_404(client, world, observation,
                                                   make_guardian, make_child):
    elsewhere = make_child(world["naran"], world["sunflower"],
                           first_name="Өөр")
    outsider = make_guardian(elsewhere, world["naran"], username="other_mother")
    login(client, outsider)

    url = attach_url(world["bataa"], observation)
    assert client.get(url).status_code == 404
    assert client.post(url, {"photo": make_jpeg()}).status_code == 404
    assert observation.media_links.count() == 0


def test_attach_user_from_another_kindergarten_gets_404(client, world,
                                                        observation):
    login(client, world["oyun"])

    url = attach_url(world["bataa"], observation)
    assert client.get(url).status_code == 404
    assert client.post(url, {"photo": make_jpeg()}).status_code == 404
    assert observation.media_links.count() == 0


def test_attach_refuses_the_childs_own_guardian(client, world, observation):
    """RFP §5.1 is the teacher's record — ``can_record_for_child``, not access.

    This family may read the observation. Adding evidence to it is a
    different permission, and the one the view has to get right.
    """
    login(client, world["bataa_mother"])

    url = attach_url(world["bataa"], observation)
    assert client.get(url).status_code == 404
    assert client.post(url, {"photo": make_jpeg()}).status_code == 404
    assert observation.media_links.count() == 0


def test_attach_refuses_an_observation_belonging_to_another_child(
    client, world, observation
):
    """A real observation id, reached through a child it does not belong to."""
    login(client, world["dulmaa"])          # entitled to both children

    url = attach_url(world["saraa"], observation)
    assert client.get(url).status_code == 404
    assert client.post(url, {"photo": make_jpeg()}).status_code == 404
    assert observation.media_links.count() == 0


def test_the_attach_screen_renders_and_works(client, world, observation):
    login(client, world["dulmaa"])
    url = attach_url(world["bataa"], observation)

    assert client.get(url).status_code == 200

    response = client.post(url, {"photo": make_jpeg(),
                                 "caption": "Барьсан цамхаг"})

    assert response.status_code == 302
    link = observation.media_links.get()
    assert link.caption == "Барьсан цамхаг"
    assert link.media_file.purpose == MediaFile.Purpose.OBSERVATION


def test_delete_teacher_from_another_group_gets_404(client, world, photo,
                                                    make_teacher, make_group):
    other = make_group(world["naran"], world["naran_year"], "Сарнай")
    stranger = make_teacher(world["naran"], other, username="stranger")
    login(client, stranger)

    assert client.post(delete_url(world["bataa"], photo)).status_code == 404
    assert MediaFile.objects.filter(pk=photo.pk).exists()


def test_delete_guardian_of_another_child_gets_404(client, world, photo,
                                                   make_guardian, make_child):
    elsewhere = make_child(world["naran"], world["sunflower"],
                           first_name="Өөр")
    outsider = make_guardian(elsewhere, world["naran"], username="other_mother")
    login(client, outsider)

    assert client.post(delete_url(world["bataa"], photo)).status_code == 404
    assert MediaFile.objects.filter(pk=photo.pk).exists()


def test_delete_user_from_another_kindergarten_gets_404(client, world, photo):
    login(client, world["oyun"])

    assert client.post(delete_url(world["bataa"], photo)).status_code == 404
    assert MediaFile.objects.filter(pk=photo.pk).exists()


def test_delete_refuses_the_childs_own_guardian(client, world, photo):
    """``delete_media`` raises ``PermissionDenied``; the view must answer 404.

    Otherwise the guardian learns the file exists and that someone else may
    remove it — RFP §21.4 is about the answer, not only the outcome.
    """
    login(client, world["bataa_mother"])

    assert client.post(delete_url(world["bataa"], photo)).status_code == 404
    assert MediaFile.objects.filter(pk=photo.pk).exists()


def test_delete_refuses_a_file_belonging_to_another_child(client, world, photo):
    """Bataa's photo, reached through Saraa's id by an entitled teacher."""
    login(client, world["dulmaa"])

    assert client.post(delete_url(world["saraa"], photo)).status_code == 404
    assert MediaFile.objects.filter(pk=photo.pk).exists()


def test_delete_refuses_a_get(client, world, photo):
    """CLAUDE.md §5 — archiving is confirmed and posted, never a link."""
    login(client, world["dulmaa"])

    assert client.get(delete_url(world["bataa"], photo)).status_code == 404
    assert MediaFile.objects.filter(pk=photo.pk).exists()


def test_the_entitled_teacher_archives_the_photo(client, world, photo):
    login(client, world["dulmaa"])

    response = client.post(delete_url(world["bataa"], photo))

    assert response.status_code == 302
    assert not MediaFile.objects.filter(pk=photo.pk).exists()
    assert MediaFile.all_objects.get(pk=photo.pk).deleted_at is not None


def test_the_signed_url_branch_is_taken_when_configured(client, world, photo,
                                                        settings, monkeypatch):
    """Production redirects instead of streaming — spec section 7.1.

    Development streams (the MinIO hostname is not resolvable from a
    browser), so without this test the redirect path would only ever run in
    production, where a mistake is expensive.
    """
    settings.MEDIA_REDIRECT_SIGNED_URL = True
    monkeypatch.setattr(
        services, "file_url",
        lambda media: "https://bucket.example.com/x.jpg?X-Amz-Signature=abc",
    )
    login(client, world["dulmaa"])

    response = client.get(serve_url(photo))

    assert response.status_code == 302
    assert response["Location"].startswith("https://bucket.example.com/")


def test_the_permission_check_runs_before_the_redirect(client, world, photo,
                                                       settings, monkeypatch):
    """RFP §21.10 — the link is minted after the check, never before."""
    settings.MEDIA_REDIRECT_SIGNED_URL = True
    called = []
    monkeypatch.setattr(services, "file_url",
                        lambda media: called.append(media) or "https://x/y.jpg")
    login(client, world["oyun"])          # another kindergarten

    assert client.get(serve_url(photo)).status_code == 404
    assert called == []
