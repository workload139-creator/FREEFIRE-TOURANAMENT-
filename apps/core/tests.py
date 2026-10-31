from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.db import OperationalError
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.core.storage import AuthenticatedCloudinaryStorage, PrivateMediaStorage


class SupportPageTests(TestCase):
    def test_support_page_is_public_and_has_contact_details(self):
        response = self.client.get(reverse("support"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Support Centre")
        self.assertContains(response, "workload139@gmail.com")
        self.assertContains(response, reverse("password_reset"))


class HealthCheckTests(TestCase):
    def test_health_check_reports_database_connection(self):
        response = self.client.get(reverse("health_check"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"status": "ok", "database": "ok"},
        )

    @patch("apps.core.views.connection.ensure_connection")
    def test_health_check_hides_database_error_details(self, ensure_connection):
        ensure_connection.side_effect = OperationalError("private database details")

        response = self.client.get(reverse("health_check"))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {"status": "unhealthy", "database": "unavailable"},
        )
        self.assertNotContains(response, "private database details", status_code=503)


@override_settings(CLOUDINARY_STORAGE={
    "CLOUD_NAME": "test-cloud",
    "API_KEY": "test-key",
    "API_SECRET": "test-secret",
    "SECURE": True,
    "MEDIA_TAG": "ff-arena-private-test",
})
class PrivateMediaStorageTests(SimpleTestCase):
    @override_settings(CLOUDINARY_MEDIA_ENABLED=False)
    def test_local_development_storage_remains_available_without_cloudinary(self):
        with TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root, MEDIA_URL="/media/"):
                storage = PrivateMediaStorage()
                saved_name = storage.save("private-proof.txt", ContentFile(b"proof"))

                self.assertTrue(storage.exists(saved_name))
                self.assertEqual(storage.open(saved_name).read(), b"proof")
                self.assertTrue(storage.path(saved_name).startswith(media_root))

    @override_settings(CLOUDINARY_MEDIA_ENABLED=True)
    def test_private_cloudinary_upload_uses_authenticated_delivery(self):
        storage = AuthenticatedCloudinaryStorage()
        with patch("apps.core.storage.cloudinary.uploader.upload") as upload:
            upload.return_value = {"public_id": "media/shop_payments/proof"}
            storage._upload("media/shop_payments/proof.png", ContentFile(b"proof"))

        self.assertEqual(upload.call_args.kwargs["type"], "authenticated")
        self.assertEqual(upload.call_args.kwargs["resource_type"], "image")

    @override_settings(CLOUDINARY_MEDIA_ENABLED=True)
    def test_kill_video_uses_video_resource_type(self):
        storage = AuthenticatedCloudinaryStorage()

        self.assertEqual(
            storage._get_resource_type("media/kill-evidence/videos/match-proof"),
            "video",
        )

    @override_settings(CLOUDINARY_MEDIA_ENABLED=True)
    def test_private_cloudinary_url_is_signed_and_secure(self):
        storage = AuthenticatedCloudinaryStorage()
        with patch("apps.core.storage.cloudinary.utils.cloudinary_url") as make_url:
            make_url.return_value = ("https://signed.example/private-proof", {})
            url = storage._get_url("media/shop_payments/proof")

        self.assertEqual(url, "https://signed.example/private-proof")
        self.assertEqual(make_url.call_args.kwargs["type"], "authenticated")
        self.assertTrue(make_url.call_args.kwargs["sign_url"])
        self.assertTrue(make_url.call_args.kwargs["secure"])
