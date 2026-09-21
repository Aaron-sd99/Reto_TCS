import unittest

from etl.transform_transactions import transform


class EtlTests(unittest.TestCase):
    def test_transform_splits_valid_and_rejected_rows(self):
        result = transform(
            [
                {
                    "transaction_id": "t-1",
                    "customer_id": "c-1",
                    "source_account": "a",
                    "destination_account": "b",
                    "amount": "10,50",
                    "currency": "usd",
                    "transaction_date": "01/09/2026",
                    "category": "",
                },
                {
                    "transaction_id": "t-2",
                    "customer_id": "",
                    "source_account": "a",
                    "destination_account": "b",
                    "amount": "",
                    "currency": "usd",
                    "transaction_date": "01/09/2026",
                    "category": "",
                },
            ]
        )
        self.assertEqual(len(result.valid), 1)
        self.assertEqual(len(result.rejected), 1)
        self.assertEqual(result.valid[0]["amount"], "10.50")
        self.assertEqual(result.valid[0]["category"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
