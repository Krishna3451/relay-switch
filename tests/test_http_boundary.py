import io
import unittest

from engine.http_boundary import permitted_request
from engine.server import Handler


class LocalBrowserBoundary(unittest.TestCase):
    def test_cli_and_same_port_loopback_browser_are_allowed(self):
        self.assertTrue(permitted_request('127.0.0.1:4318', method='POST'))
        self.assertTrue(permitted_request('localhost:4318', 'http://localhost:4318', method='POST'))
        self.assertTrue(permitted_request('127.0.0.1:4318', method='GET', fetch_site='cross-site'))

    def test_foreign_null_rebinding_and_other_local_port_are_refused(self):
        for host, origin in [('attacker.example:4318', None), ('127.0.0.1:4318', 'null'),
                             ('127.0.0.1:4318', 'https://attacker.example'),
                             ('localhost:4318', 'http://localhost:9999'),
                             ('localhost:4318', 'http://127.0.0.1:4318'),
                             ('localhost:4318', 'http://localhost:4318/evil'),
                             ('user@localhost:4318', None), ('localhost:invalid', None)]:
            with self.subTest(host=host, origin=origin):
                self.assertFalse(permitted_request(host, origin, method='POST'))
        self.assertFalse(permitted_request('localhost:4318', method='POST', fetch_site='cross-site'))

    def test_negative_body_length_is_rejected_without_blocking_read(self):
        handler = Handler.__new__(Handler)
        handler.headers = {'content-length': '-1'}
        class NeverRead:
            def read(self, size):
                raise AssertionError('Negative body lengths must never read until EOF')
        handler.rfile = NeverRead()
        with self.assertRaises(ValueError):
            handler.body()

    def test_non_object_json_is_rejected_at_the_boundary(self):
        handler = Handler.__new__(Handler)
        handler.headers = {'content-length': '2'}
        handler.rfile = io.BytesIO(b'[]')
        with self.assertRaises(ValueError):
            handler.body()
