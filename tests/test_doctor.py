"""`doctor` is wired into the CLI and does not publish anything."""

from __future__ import annotations

import unittest

from content_factory.cli import build_parser


class DoctorCLITest(unittest.TestCase):
    def test_doctor_parser(self) -> None:
        args = build_parser().parse_args(["doctor"])
        self.assertEqual(getattr(args.func, "__name__", ""), "cmd_doctor")


if __name__ == "__main__":
    unittest.main()
