"""Tests de validación de seguridad del servidor (sin red externa)."""
import http.client
import json
import os
import tempfile
import threading
import unittest

from scouting import server
from scouting.server import App, HttpError, Request, validate_config


class _Upd:
    def snapshot(self):
        return {}


class ConfigValidation(unittest.TestCase):
    def test_valid(self):
        c = validate_config({"update_interval_hours": 12, "stats_days": 30, "batch_size": 50,
                             "extra_leaderboard_ids": [1001], "api_key": "abc"})
        self.assertEqual(c["update_interval_hours"], 12.0)

    def test_invalid(self):
        bad = [{"update_interval_hours": 0}, {"update_interval_hours": 721}, {"update_interval_hours": "5"},
               {"stats_days": 0}, {"stats_days": 366}, {"stats_days": 3.5}, {"batch_size": 1001},
               {"batch_size": True}, {"extra_leaderboard_ids": "1001"}, {"extra_leaderboard_ids": [1, "x"]},
               {"api_key": "x" * 201}, {"api_key": 5}]
        for b in bad:
            with self.assertRaises(HttpError, msg=b) as cm:
                validate_config(dict(b))
            self.assertEqual(cm.exception.status, 400)


class ImportOldValidation(unittest.TestCase):
    def _call(self, path):
        app = App(None, _Upd(), 0)
        return app.import_old(Request(None, {}, json.dumps({"path": path, "dry_run": True}).encode()))

    def test_rejects_dir_and_extension(self):
        with tempfile.TemporaryDirectory() as d:
            for p in (d, os.path.join(d, "nope.db")):
                with self.assertRaises(HttpError):
                    self._call(p)
            txt = os.path.join(d, "a.txt")
            open(txt, "w").close()
            with self.assertRaises(HttpError) as cm:
                self._call(txt)
            self.assertEqual(cm.exception.status, 400)


class HttpHardening(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = App(None, _Upd(), 0)
        cls.httpd = server.serve(cls.app, "127.0.0.1", 0)
        cls.port = cls.httpd.server_address[1]
        cls.app.port = cls.port
        cls.httpd.RequestHandlerClass = server.make_handler(cls.app)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def _req(self, method, path, body=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        h = {"Host": f"127.0.0.1:{self.port}"}
        h.update(headers or {})
        c.putrequest(method, path, skip_host=True)
        for k, v in h.items():
            c.putheader(k, v)
        c.endheaders(body)
        r = c.getresponse()
        data = r.read()
        c.close()
        return r, data

    def test_bad_content_length(self):
        for cl in ("abc", "-5"):
            r, _ = self._req("POST", "/api/config", None, {"Content-Type": "application/json", "Content-Length": cl})
            self.assertEqual(r.status, 400, cl)

    def test_bad_query_int(self):
        r, _ = self._req("GET", "/api/climbers?days=abc")
        self.assertEqual(r.status, 400)

    def test_cross_site_get_rejected(self):
        r, _ = self._req("GET", "/api/climbers", headers={"Sec-Fetch-Site": "cross-site"})
        self.assertEqual(r.status, 403)

    def test_security_headers(self):
        r, _ = self._req("GET", "/api/nope")
        self.assertIn("frame-ancestors 'none'", r.getheader("Content-Security-Policy"))
        self.assertEqual(r.getheader("X-Frame-Options"), "DENY")
        self.assertEqual(r.getheader("Referrer-Policy"), "no-referrer")




class CalibrationSave(unittest.TestCase):
    def test_keys_and_invert(self):
        from unittest import mock
        app = App(None, _Upd(), 0)
        base = {"x_min": -1, "x_max": 1, "y_min": -1, "y_max": 1}
        with mock.patch("scouting.minimap.save_calibration") as sv:
            cal = app.map_calibration_save(Request(None, {}, json.dumps(
                {"calibration": dict(base, invert_y=True, evil="x")}).encode()))
            self.assertEqual(cal, dict(base, invert_y=True))
            for bad in (dict(base, invert_x="yes"), dict(base, x_min=2)):
                with self.assertRaises(HttpError):
                    app.map_calibration_save(Request(None, {}, json.dumps({"calibration": bad}).encode()))
            self.assertEqual(sv.call_count, 1)


if __name__ == "__main__":
    unittest.main()
