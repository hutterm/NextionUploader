import unittest
from types import SimpleNamespace
from unittest.mock import patch

import serial

from Nexus import Nexus


class FakeSerial:
    def __init__(self, *, open_fail_bauds=None, invalid_bauds=None, responses_by_baud=None):
        self.port = None
        self._baudrate = None
        self.timeout = None
        self.is_open = False
        self.open_calls = []
        self.write_calls = []
        self._open_fail_bauds = set(open_fail_bauds or set())
        self._invalid_bauds = set(invalid_bauds or set())
        self._responses_by_baud = responses_by_baud or {}
        self._response_index = {}

    @property
    def baudrate(self):
        return self._baudrate

    @baudrate.setter
    def baudrate(self, value):
        if value in self._invalid_bauds:
            raise ValueError("unsupported baudrate")
        self._baudrate = value

    @property
    def in_waiting(self):
        responses = self._responses_by_baud.get(self._baudrate, [])
        if isinstance(responses, bytes):
            responses = [responses]
        index = self._response_index.get(self._baudrate, 0)
        if index >= len(responses):
            return 0
        return len(responses[index])

    def open(self):
        self.open_calls.append(self._baudrate)
        if self._baudrate in self._open_fail_bauds:
            raise serial.SerialException("cannot open port at this baudrate")
        self.is_open = True

    def close(self):
        self.is_open = False

    def reset_input_buffer(self):
        return None

    def write(self, data):
        self.write_calls.append(data)
        return len(data)

    def read_until(self, expected=b"\xff\xff\xff"):
        responses = self._responses_by_baud.get(self._baudrate, [])
        if isinstance(responses, bytes):
            responses = [responses]
        index = self._response_index.get(self._baudrate, 0)
        if index >= len(responses):
            return b""
        self._response_index[self._baudrate] = index + 1
        return responses[index]

    def read(self, size=1):
        if size == 1:
            return Nexus.NXACK
        return b"\x00" * size


class NexusConnectTests(unittest.TestCase):
    @staticmethod
    def make_comok_response():
        return b"comok 1,0-123,NX3224K024,155,32,SN123456,16777216\xff\xff\xff"

    def test_connect_continues_baud_scan_when_open_fails(self):
        fake_serial = FakeSerial(
            open_fail_bauds={9600},
            responses_by_baud={921600: self.make_comok_response()},
        )
        with patch("Nexus.availablePorts", return_value=[SimpleNamespace(device="COM9")]):
            with patch("Nexus.serial.Serial", return_value=fake_serial):
                nexus = Nexus(port="COM9", connect=False, connectSpeed=9600)

        self.assertTrue(nexus.connect())
        self.assertGreaterEqual(len(fake_serial.open_calls), 2)
        self.assertEqual(fake_serial.open_calls[0], 9600)
        self.assertEqual(fake_serial.open_calls[1], 921600)

    def test_connect_handles_unsupported_baudrate_and_continues_scan(self):
        fake_serial = FakeSerial(
            invalid_bauds={9600},
            responses_by_baud={921600: self.make_comok_response()},
        )
        with patch("Nexus.availablePorts", return_value=[SimpleNamespace(device="COM9")]):
            with patch("Nexus.serial.Serial", return_value=fake_serial):
                nexus = Nexus(port="COM9", connect=False, connectSpeed=9600)

        self.assertTrue(nexus.connect())
        self.assertIn(921600, fake_serial.open_calls)

    def test_connect_skips_noise_and_uses_later_comok_frame(self):
        fake_serial = FakeSerial(
            responses_by_baud={
                9600: [b"garbage\xff\xff\xff", self.make_comok_response()],
            }
        )
        with patch("Nexus.availablePorts", return_value=[SimpleNamespace(device="COM9")]):
            with patch("Nexus.serial.Serial", return_value=fake_serial):
                nexus = Nexus(port="COM9", connect=False, connectSpeed=9600)

        self.assertTrue(nexus.connect())
        self.assertEqual(nexus.connectSpeed, 9600)


if __name__ == "__main__":
    unittest.main()
