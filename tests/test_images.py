"""Tests del proxy-caché de imágenes (sin red: el opener se inyecta)."""
import http.client
import os
import shutil
import tempfile
import threading
import unittest

from scouting import images, server
from scouting.server import App

PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6360f8ffff3f0005fe02fea7d6a3c40000000049454e44ae426082")


class _Upd:
    def snapshot(self):
        return {}


class _CacheCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._old = images.CACHE_DIR
        images.CACHE_DIR = self.tmp
        images._FAILED.clear()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.addCleanup(setattr, images, "CACHE_DIR", self._old)


class ImageProxy(_CacheCase):
    def test_safe_name(self):
        self.assertEqual(images.safe_name("wiki", "Mo_&_Krill_vertical.png"), "Mo_&_Krill_vertical.png")
        self.assertEqual(images.safe_name("api", "heroes/abrams_sm.webp"), "heroes/abrams_sm.webp")
        for bad in ["../x.png", "a/../../b.png", "/etc/x.png", "x.exe", "x.png?y=1", "C:x.png", "", "a\b.png"]:
            self.assertIsNone(images.safe_name("wiki", bad), bad)
            self.assertIsNone(images.safe_name("api", bad), bad)
        self.assertIsNone(images.safe_name("evil", "x.png"))
        self.assertIsNone(images.safe_name("wiki", "sub/x.png"))
        self.assertIsNone(images.safe_name("api", "a/b/c/d.png"))

    def test_fetch_caches_and_reuses(self):
        calls = []

        def opener(url):
            calls.append(url)
            return 200, {"Content-Type": "image/png"}, PNG_1PX
        self.assertEqual(images.get("wiki", "Walker_Icon.png", opener), (PNG_1PX, "image/png"))
        self.assertEqual(images.get("wiki", "Walker_Icon.png", opener), (PNG_1PX, "image/png"))
        self.assertEqual(calls, ["https://cdn.deadlock.wiki/Walker_Icon.png"])
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "wiki", "Walker_Icon.png")))

    def test_upstream_url_is_quoted(self):
        calls = []

        def opener(url):
            calls.append(url)
            return 200, {"Content-Type": "image/png"}, PNG_1PX
        images.get("wiki", "Mo_&_Krill_vertical.png", opener)
        images.get("api", "heroes/inferno_sm.webp", opener)
        self.assertEqual(calls, ["https://cdn.deadlock.wiki/Mo_%26_Krill_vertical.png",
                                 "https://assets-bucket.deadlock-api.com/assets-api-res/images/heroes/inferno_sm.webp"])

    def _written(self):
        return [f for _, _, fs in os.walk(self.tmp) for f in fs]

    def test_rejects_non_image_and_oversize(self):
        self.assertIsNone(images.get("wiki", "a.png", lambda u: (200, {"Content-Type": "text/html"}, b"<html>")))
        big = b"x" * (images.MAX_BYTES + 1)
        self.assertIsNone(images.get("wiki", "b.png", lambda u: (200, {"Content-Type": "image/png"}, big)))
        self.assertEqual(self._written(), [])

    def test_failure_is_remembered(self):
        calls = []

        def opener(url):
            calls.append(url)
            return 404, {}, b""
        self.assertIsNone(images.get("wiki", "nope.png", opener))
        self.assertIsNone(images.get("wiki", "nope.png", opener))
        self.assertEqual(len(calls), 1)

    def test_opener_exception_is_failure(self):
        def opener(url):
            raise OSError("sin red")
        self.assertIsNone(images.get("wiki", "x.png", opener))

    def test_invalid_name_never_calls_opener(self):
        def opener(url):
            raise AssertionError("no debe llamarse")
        self.assertIsNone(images.get("wiki", "../x.png", opener))


class ImageRoute(_CacheCase):
    def setUp(self):
        super().setUp()
        app = App(None, _Upd(), 0)
        self.httpd = server.serve(app, "127.0.0.1", 0)
        self.port = self.httpd.server_address[1]
        app.port = self.port
        self.httpd.RequestHandlerClass = server.make_handler(app)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(self._stop)

    def _stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def _req(self, path, host=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.putrequest("GET", path, skip_host=True)
        c.putheader("Host", host or f"127.0.0.1:{self.port}")
        c.endheaders()
        r = c.getresponse()
        data = r.read()
        c.close()
        return r, data

    def test_http_route(self):
        r, _ = self._req("/img/wiki/..%2Fx.png")
        self.assertEqual(r.status, 404)
        r, _ = self._req("/img/evil/x.png")
        self.assertEqual(r.status, 404)
        os.makedirs(os.path.join(self.tmp, "wiki"))
        with open(os.path.join(self.tmp, "wiki", "Walker_Icon.png"), "wb") as f:
            f.write(PNG_1PX)
        r, data = self._req("/img/wiki/Walker_Icon.png")
        self.assertEqual(r.status, 200)
        self.assertEqual(data, PNG_1PX)
        self.assertEqual(r.getheader("Content-Type"), "image/png")
        self.assertIn("max-age=604800", r.getheader("Cache-Control"))
        self.assertEqual(r.getheader("X-Content-Type-Options"), "nosniff")
        r, _ = self._req("/img/wiki/Walker_Icon.png", host="evil.com")
        self.assertEqual(r.status, 403)


if __name__ == "__main__":
    unittest.main()
