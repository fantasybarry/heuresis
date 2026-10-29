"""Two workstations share one upstream stream and see only their own symbols."""

import os
import threading
import unittest
from unittest.mock import patch

from nomisma import pool


def fake_stream(symbols, on_event, stop, on_status=None):
    on_status("live")
    while not stop.wait(0.02):
        for symbol in symbols:
            on_event({"T": "t", "S": symbol, "p": 1.0})


class PoolTest(unittest.TestCase):
    def setUp(self):
        self.pool = pool.Pool("x" * 16)
        self.server = pool._Server(("127.0.0.1", 0), pool._Handler)
        self.server.pool = self.pool
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.env = {"NOMISMA_POOL": "127.0.0.1:%d" % self.server.server_address[1], "NOMISMA_POOL_TOKEN": "x" * 16}

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def workstation(self, symbol, stop):
        seen, states = set(), []
        def on_event(event):
            seen.add(event["S"])
        thread = threading.Thread(target=pool.stream_pool, args=([symbol], on_event, stop, states.append), daemon=True)
        thread.start()
        return seen, states, thread

    def test_fan_out_filters_by_symbol(self):
        with patch.dict(os.environ, self.env), patch.object(pool, "stream_live", fake_stream):
            threading.Thread(target=self.pool.run, daemon=True).start()
            stop = threading.Event()
            a_seen, a_states, a = self.workstation("AAPL", stop)
            b_seen, b_states, b = self.workstation("TSLA", stop)
            for _ in range(100):
                if a_seen and b_seen:
                    break
                stop.wait(0.05)
            stop.set()
            a.join(2), b.join(2)
        self.assertEqual(a_seen, {"AAPL"})
        self.assertEqual(b_seen, {"TSLA"})
        self.assertIn("live", a_states)
        self.assertIn("live", b_states)

    def test_quiet_workstation_that_hangs_up_is_dropped(self):
        # No upstream events flow, so only the hang-up check can notice the closed connection.
        with patch.dict(os.environ, self.env):
            stop = threading.Event()
            _, _, thread = self.workstation("AAPL", stop)
            for _ in range(40):
                if self.pool.clients:
                    break
                stop.wait(0.05)
            self.assertEqual(len(self.pool.clients), 1)
            stop.set()
            thread.join(2)
            for _ in range(60):
                if not self.pool.clients:
                    break
                threading.Event().wait(0.05)
        self.assertEqual(self.pool.clients, {})

    def test_wrong_token_is_rejected(self):
        with patch.dict(os.environ, dict(self.env, NOMISMA_POOL_TOKEN="y" * 16)):
            with self.assertRaisesRegex(ValueError, "token"):
                pool.stream_pool(["AAPL"], lambda event: None, threading.Event())


if __name__ == "__main__":
    unittest.main()
