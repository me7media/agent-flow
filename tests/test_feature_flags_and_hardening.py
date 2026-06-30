from __future__ import annotations

import unittest
from fastapi.testclient import TestClient

from app import main


class FeatureFlagAndHardeningTests(unittest.TestCase):
    def setUp(self):
        self.original_iot_enabled = main.config.IOT_ENABLED
        self.original_http_hosts = list(main.config.HTTP_ACTION_ALLOWED_HOSTS)
        self.original_email_enabled = main.config.EMAIL_ACTION_ENABLED

    def tearDown(self):
        main.config.IOT_ENABLED = self.original_iot_enabled
        main.config.HTTP_ACTION_ALLOWED_HOSTS = self.original_http_hosts
        main.config.EMAIL_ACTION_ENABLED = self.original_email_enabled

    def test_iot_disabled_is_hidden_from_public_api(self):
        main.config.IOT_ENABLED = False
        client = TestClient(main.app)

        health = client.get('/api/health').json()
        registry = client.get('/api/registry').json()
        iot_response = client.get('/api/iot/pipelines')

        self.assertFalse(health['features']['iot'])
        self.assertEqual(health['settings']['iotSources'], [])
        self.assertEqual(health['settings']['iotActions'], [])
        self.assertFalse(any(flow.get('category') == 'iot' for flow in registry['flows']))
        self.assertEqual(iot_response.status_code, 404)

    def test_workspace_and_git_routes_are_removed(self):
        client = TestClient(main.app)

        self.assertEqual(client.post('/api/workspace/scan', json={}).status_code, 404)
        self.assertEqual(client.post('/api/workspace/read', json={}).status_code, 404)
        self.assertEqual(client.post('/api/workspace/write', json={}).status_code, 404)
        self.assertEqual(client.post('/api/git/info', json={}).status_code, 404)
        self.assertEqual(client.get('/api/iot/adapters').status_code, 200)

    def test_http_and_email_actions_are_disabled_without_explicit_flags(self):
        main.config.HTTP_ACTION_ALLOWED_HOSTS = []
        main.config.EMAIL_ACTION_ENABLED = False
        client = TestClient(main.app)

        http_response = client.post('/api/actions/http', json={'url': 'https://example.com'})
        email_response = client.post('/api/actions/email/send', json={'to': 'a@example.com', 'subject': 'x', 'body': 'x'})

        self.assertEqual(http_response.status_code, 403)
        self.assertEqual(email_response.status_code, 403)


if __name__ == '__main__':
    unittest.main()
