"""Тесты монетизации: заказы, payload, сценарии бота продажи рекламы (без сети)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from content_factory.monetization import (
    AdOrderStore,
    ad_order_to_post,
    MonetizationError,
    channel_offer,
    load_offers,
    make_payload,
    parse_payload,
    plan_update_actions,
)

CONFIG = """
admin_chat_id_env: TELEGRAM_ADMIN_CHAT_ID
currency: XTR
min_amount: 1
channels:
  ai-news:
    title: "AI News (US)"
    tariffs:
      "1/24": {price: 150, description: "1 пост, 24 часа"}
      "2/48": {price: 250, description: "2 поста, 48 часов"}
  tech-ai-es:
    title: "ES AI News (LatAm)"
    tariffs:
      "1/24": {price: 100, description: "1 publicación, 24 h"}
"""


class MonetizationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.db_path = self.root / "data" / "factory.sqlite3"
        self.config_path = self.root / "monetization.yaml"
        self.config_path.write_text(CONFIG, encoding="utf-8")
        self.store = AdOrderStore(self.db_path)
        self.addCleanup(self.store.close)
        self.raw, self.offers = load_offers(self.config_path)
        self.queue_dir = self.root / "ads"
        self.admin = "999"

    # helpers -----------------------------------------------------------
    def start(self, user_id=111):
        return plan_update_actions(
            {"update_id": 1, "message": {"text": "/start", "chat": {"id": user_id}, "from": {"id": user_id, "username": "buyer"}}},
            self.store,
            self.offers,
            self.admin,
            self.queue_dir,
        )

    def callback(self, data, user_id=111):
        return plan_update_actions(
            {"update_id": 2, "callback_query": {"id": "cb1", "data": data, "from": {"id": user_id}, "message": {"chat": {"id": user_id}}}},
            self.store,
            self.offers,
            self.admin,
            self.queue_dir,
        )

    def buy(self):
        self.callback("ch:ai-news")
        actions = self.callback("buy:ai-news:1-24")
        invoice = actions[-1]
        order = self.store.by_payload(invoice["payload"]["payload"])
        return order, invoice

    def pay(self, order):
        return plan_update_actions(
            {
                "update_id": 3,
                "message": {
                    "chat": {"id": 111},
                    "from": {"id": 111, "username": "buyer"},
                    "successful_payment": {
                        "invoice_payload": order.payload,
                        "telegram_payment_charge_id": "chg",
                        "total_amount": order.amount,
                        "currency": "XTR",
                    },
                },
            },
            self.store,
            self.offers,
            self.admin,
            self.queue_dir,
        )


class ConfigAndPayloadTests(MonetizationTestCase):
    def test_load_offers(self):
        offer = channel_offer(self.offers, "ai-news")
        self.assertEqual(offer.title, "AI News (US)")
        self.assertEqual(offer.tariff("1/24").price, 150)
        self.assertIsNone(offer.tariff("nope"))

    def test_invalid_config(self):
        bad = self.config_path.with_name("bad.yaml")
        bad.write_text("channels: {}\n", encoding="utf-8")
        with self.assertRaises(MonetizationError):
            load_offers(bad)
        cheap = self.config_path.with_name("cheap.yaml")
        cheap.write_text(
            "channels:\n  a:\n    tariffs:\n      '1/24': {price: 0}\n", encoding="utf-8"
        )
        with self.assertRaises(MonetizationError):
            load_offers(cheap)

    def test_payload_roundtrip(self):
        payload = make_payload("ai-news", "1/24", "abc123")
        parsed = parse_payload(payload)
        self.assertEqual(parsed["channel_id"], "ai-news")
        self.assertEqual(parsed["tariff"], "1-24")
        self.assertLessEqual(len(payload), 128)
        self.assertIsNone(parse_payload("bad"))
        self.assertIsNone(parse_payload("ad:x:y"))


class StoreTests(MonetizationTestCase):
    def test_crud_and_stats(self):
        order = self.store.create("ai-news", "1/24", 150, buyer_id="111")
        self.assertEqual(self.store.get(order.id).status, "pending_invoice")
        self.store.update(order.id, status="awaiting_text", paid_at="now")
        self.assertEqual(self.store.latest_for_buyer("111", "awaiting_text").id, order.id)
        self.store.update(order.id, status="approved", ad_text="Текст")
        stats = self.store.stats()
        self.assertEqual(stats["by_status"]["approved"], 1)
        self.assertEqual(stats["paid_stars"], 150)
        self.assertEqual(len(self.store.list(status="approved")), 1)


class AdPostTests(MonetizationTestCase):
    def test_order_to_post(self):
        order = self.store.create("ai-news", "1/24", 150, buyer_id="111")
        order = self.store.update(order.id, ad_text="Текст рекламы", status="approved")
        post = ad_order_to_post(order)
        self.assertEqual(post.channel_id, "ai-news")
        self.assertEqual(post.text, "Текст рекламы")
        self.assertEqual(post.meta["ad_order_id"], order.id)
        self.assertEqual(post.id, f"ad-{order.id}")
        with self.assertRaises(MonetizationError):
            ad_order_to_post(self.store.create("ai-news", "1/24", 150))


class RefundTests(MonetizationTestCase):
    def test_refund_calls_api(self):
        from content_factory.monetization import refund_star_payment

        with mock.patch("content_factory.monetization.urllib.request.urlopen") as mocked:
            mocked.return_value.__enter__.return_value.read.return_value = b'{"ok": true}'
            data = refund_star_payment("token", 111, "chg")
        self.assertEqual(data, {"ok": True})
        body = mocked.call_args.args[0].data.decode("utf-8")
        self.assertIn("refundStarPayment", mocked.call_args.args[0].full_url)
        self.assertIn("chg", body)

    def test_refund_requires_charge(self):
        from content_factory.monetization import refund_star_payment

        with self.assertRaises(MonetizationError):
            refund_star_payment("token", 111, "")


class FlowTests(MonetizationTestCase):
    def test_start_shows_channels(self):
        actions = self.start()
        self.assertEqual(actions[0]["method"], "sendMessage")
        keyboard = actions[0]["payload"]["reply_markup"]["inline_keyboard"]
        self.assertTrue(any("ai-news" in row[0]["callback_data"] for row in keyboard))

    def test_buy_creates_invoice(self):
        order, invoice = self.buy()
        self.assertIsNotNone(order)
        self.assertEqual(invoice["method"], "sendInvoice")
        payload = invoice["payload"]
        self.assertEqual(payload["currency"], "XTR")
        self.assertEqual(payload["provider_token"], "")
        self.assertEqual(payload["prices"][0]["amount"], 150)
        self.assertEqual(self.store.get(order.id).status, "pending_invoice")

    def test_pre_checkout_and_payment(self):
        order, invoice = self.buy()
        checkout = plan_update_actions(
            {"update_id": 4, "pre_checkout_query": {"id": "pc1", "invoice_payload": order.payload}},
            self.store,
            self.offers,
            self.admin,
            self.queue_dir,
        )
        self.assertTrue(checkout[0]["payload"]["ok"])
        actions = self.pay(order)
        self.assertEqual(self.store.get(order.id).status, "awaiting_text")
        self.assertEqual(self.store.get(order.id).payment_charge_id, "chg")
        self.assertTrue(any("Оплата получена" in action["payload"].get("text", "") for action in actions))
        self.assertTrue(any(str(action["payload"].get("chat_id")) == self.admin for action in actions))

    def test_text_moderation_and_approve(self):
        order, _ = self.buy()
        self.pay(order)
        actions = plan_update_actions(
            {"update_id": 5, "message": {"text": "Купите наш продукт", "chat": {"id": 111}, "from": {"id": 111}}},
            self.store,
            self.offers,
            self.admin,
            self.queue_dir,
        )
        self.assertEqual(self.store.get(order.id).status, "moderation")
        admin_msg = [a for a in actions if str(a["payload"].get("chat_id")) == self.admin][0]
        self.assertIn("adok:", json.dumps(admin_msg["payload"], ensure_ascii=False))
        approved = self.callback(f"adok:{order.id}", user_id=999)
        updated = self.store.get(order.id)
        self.assertEqual(updated.status, "approved")
        queue_file = Path(updated.queue_file)
        self.assertTrue(queue_file.is_file())
        self.assertEqual(json.loads(queue_file.read_text(encoding="utf-8"))["ad_text"], "Купите наш продукт")
        self.assertTrue(any("одобрена" in action["payload"].get("text", "").lower() for action in approved))

    def test_reject_and_non_admin(self):
        order, _ = self.buy()
        self.pay(order)
        plan_update_actions(
            {"update_id": 6, "message": {"text": "Текст", "chat": {"id": 111}, "from": {"id": 111}}},
            self.store,
            self.offers,
            self.admin,
            self.queue_dir,
        )
        denied = self.callback(f"adok:{order.id}", user_id=111)
        self.assertTrue(any("прав" in action["payload"].get("text", "") for action in denied))
        self.callback(f"adno:{order.id}", user_id=999)
        self.assertEqual(self.store.get(order.id).status, "rejected")

    def test_payment_unknown_payload_ignored(self):
        actions = plan_update_actions(
            {"update_id": 7, "message": {"successful_payment": {"invoice_payload": "unknown"}}},
            self.store,
            self.offers,
            self.admin,
            self.queue_dir,
        )
        self.assertEqual(actions, [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
