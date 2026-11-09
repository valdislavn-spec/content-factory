"""Travelpayouts finance API: баланс, выплата, история (моки)."""

from __future__ import annotations

import unittest
from unittest import mock

from content_factory.integrations.travelpayouts import TravelpayoutsClient, TravelpayoutsError


class TravelpayoutsFinanceTest(unittest.TestCase):
    def client(self):
        return TravelpayoutsClient(token="tok", marker="674170", trs="597672")

    def test_balance_and_payout(self):
        responses = {
            "get_user_balance": {"balance": {"usd": "12.50", "eur": "10.00", "rub": "1000"}},
            "get_user_next_payout": {"next_payout": {"usd": "5.00"}},
            "get_user_payments": [{"amount": "1.00", "currency": "usd"}],
        }

        def fake_finance(method, params=None):
            return responses[method]

        with mock.patch.object(TravelpayoutsClient, "_finance", side_effect=fake_finance):
            client = self.client()
            self.assertEqual(client.balance()["usd"], "12.50")
            self.assertEqual(client.next_payout()["usd"], "5.00")
            self.assertEqual(len(client.payments()), 1)

    def test_no_token_raises(self):
        client = TravelpayoutsClient(token="", marker="", trs="")
        with self.assertRaises(TravelpayoutsError):
            client.balance()


if __name__ == "__main__":
    unittest.main()
