from django.test import SimpleTestCase
from django.urls import reverse


class LivenessTest(SimpleTestCase):
    def test_liveness_returns_ok(self):
        response = self.client.get(reverse("health-live"))

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_liveness_rejects_non_get_requests(self):
        response = self.client.post(reverse("health-live"))

        assert response.status_code == 405
