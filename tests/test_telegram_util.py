from __future__ import annotations

import unittest

from allampapir_ertesito.telegram_util import extract_chats


class TelegramUtilTests(unittest.TestCase):
    def test_extracts_group_from_my_chat_member(self) -> None:
        payload = {
            "ok": True,
            "result": [
                {
                    "update_id": 1,
                    "my_chat_member": {
                        "chat": {
                            "id": -1001234567890,
                            "type": "supergroup",
                            "title": "Állampapír-bot",
                        }
                    },
                },
                {
                    "update_id": 2,
                    "message": {
                        "chat": {
                            "id": 42,
                            "type": "private",
                            "first_name": "Gyuri",
                        }
                    },
                },
                {
                    "update_id": 3,
                    "message": {
                        "chat": {
                            "id": -1001234567890,
                            "type": "supergroup",
                            "title": "Állampapír-bot",
                        }
                    },
                },
            ],
        }
        chats = extract_chats(payload)
        self.assertEqual(len(chats), 2)
        self.assertEqual(chats[0]["id"], -1001234567890)
        self.assertEqual(chats[0]["type"], "supergroup")
        self.assertEqual(chats[0]["title"], "Állampapír-bot")
        self.assertEqual(chats[1]["id"], 42)

    def test_ignores_invalid_updates(self) -> None:
        payload = {"ok": True, "result": [None, {}, {"message": {}}, {"message": {"chat": {}}}]}
        self.assertEqual(extract_chats(payload), [])


if __name__ == "__main__":
    unittest.main()
