import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from models import Alert, Event, ModelPrediction, SimulationStatus, UserRiskProfile
from services.csv_import_service import (
    MAX_CSV_BYTES,
    MAX_CSV_ROWS,
    CSVImportError,
    import_transactions,
    parse_transaction_csv,
)
from services.event_simulator import simulator
from services.feature_engineering import EVENT_TYPE_INDEX


class CSVImportTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.session_factory = sessionmaker(bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        Base.metadata.drop_all(self.engine)
        Base.metadata.create_all(self.engine)
        self.db = self.session_factory()
        self.db.add(SimulationStatus(is_running=False, events_generated=12, anomalies_injected=3))
        self.db.commit()

    def tearDown(self):
        self.db.close()

    async def test_valid_paysim_csv_is_analyzed_and_persisted(self):
        content = (
            "step,type,amount,nameOrig,oldbalanceOrg,newbalanceOrig,oldbalanceDest,newbalanceDest,isFraud\n"
            "1,TRANSFER,1000000,C100,0,0,0,0,1\n"
        ).encode()

        result = await import_transactions(self.db, "paysim.csv", content)

        event = self.db.query(Event).one()
        prediction = self.db.query(ModelPrediction).one()
        self.assertEqual((result.total_rows, result.analyzed_rows, result.rejected_rows), (1, 1, 0))
        self.assertEqual(result.detected_anomalies, 1)
        self.assertTrue(event.is_anomaly)
        self.assertEqual(event.event_type, "Transaction")
        self.assertEqual(event.metadata_json["import"]["dataset_label_is_fraud"], True)
        self.assertNotIn("dataset_label_is_fraud", prediction.features)
        self.assertEqual(self.db.query(SimulationStatus).one().events_generated, 12)

    async def test_dataset_label_does_not_change_model_prediction(self):
        content = (
            "event_type,user_id,amount,timestamp,isFraud\n"
            "Transaction,user-a,1000000,2025-01-01T12:00:00,0\n"
            "Transaction,user-b,1000000,2025-01-01T12:00:00,1\n"
        ).encode()

        result = await import_transactions(self.db, "labels.csv", content)

        events = self.db.query(Event).order_by(Event.id).all()
        predictions = self.db.query(ModelPrediction).order_by(ModelPrediction.id).all()
        self.assertEqual(result.analyzed_rows, 2)
        self.assertEqual(events[0].anomaly_score, events[1].anomaly_score)
        self.assertEqual(events[0].is_anomaly, events[1].is_anomaly)
        self.assertEqual(predictions[0].features, predictions[1].features)
        self.assertEqual(
            [event.metadata_json["import"]["dataset_label_is_fraud"] for event in events],
            [False, True],
        )

    async def test_supported_transaction_event_types_use_canonical_model_types(self):
        content = (
            "event_type,user_id,amount\n"
            "Payment,user-pay,25\n"
            "Transaction,user-txn,30\n"
            "Transfer,user-transfer,35\n"
            "Withdrawal,user-withdrawal,40\n"
            "Purchase,user-purchase,45\n"
        ).encode()

        result = await import_transactions(self.db, "transaction-types.csv", content)

        events = self.db.query(Event).order_by(Event.id).all()
        predictions = self.db.query(ModelPrediction).order_by(ModelPrediction.id).all()
        self.assertEqual(result.total_rows, 5)
        self.assertEqual(result.analyzed_rows, 5)
        self.assertEqual(result.invalid_rows, 0)
        self.assertEqual(result.rejected_rows, 0)
        self.assertEqual(
            [event.event_type for event in events],
            ["Payment", "Transaction", "Transaction", "Transaction", "Transaction"],
        )
        self.assertEqual(
            [event.metadata_json.get("source_event_type") for event in events],
            [None, None, "Transfer", "Withdrawal", "Purchase"],
        )
        self.assertEqual(
            [prediction.features["event_type_encoded"] for prediction in predictions],
            [
                float(EVENT_TYPE_INDEX["Payment"]),
                float(EVENT_TYPE_INDEX["Transaction"]),
                float(EVENT_TYPE_INDEX["Transaction"]),
                float(EVENT_TYPE_INDEX["Transaction"]),
                float(EVENT_TYPE_INDEX["Transaction"]),
            ],
        )

    async def test_invalid_and_missing_event_types_are_rejected(self):
        content = (
            "event_type,user_id,amount\n"
            "Crypto Transfer,user-invalid,10\n"
            ",user-missing,10\n"
            "Transaction,user-valid,10\n"
        ).encode()

        result = await import_transactions(self.db, "invalid-types.csv", content)

        self.assertEqual(result.total_rows, 3)
        self.assertEqual(result.analyzed_rows, 1)
        self.assertEqual(result.invalid_rows, 2)
        self.assertEqual(result.rejected_rows, 2)
        self.assertEqual(
            [rejection.reason for rejection in result.rejections],
            [
                "unsupported event_type: Crypto Transfer. Use an application event type "
                "or one of Payment, Transaction, Transfer, Withdrawal, Purchase.",
                "event_type is required",
            ],
        )

    def test_ten_thousand_supported_types_parse_without_rejection(self):
        event_types = ("Payment", "Transaction", "Transfer", "Withdrawal", "Purchase")
        rows = ["event_type,user_id,amount"]
        rows.extend(
            f"{event_types[index % len(event_types)]},user-{index},10"
            for index in range(10000)
        )

        records, rejections, total_rows = parse_transaction_csv(
            "synthetic-transactions.csv",
            ("\n".join(rows) + "\n").encode(),
        )

        self.assertEqual(total_rows, 10000)
        self.assertEqual(len(records), 10000)
        self.assertEqual(rejections, [])
        self.assertEqual(
            {record["event_type"] for record in records},
            {"Payment", "Transaction"},
        )

    async def test_invalid_amounts_are_rejected_with_actionable_reasons(self):
        content = (
            "event_type,user_id,amount\n"
            "Transaction,user-negative,-1\n"
            "Transaction,user-nan,NaN\n"
            "Transaction,user-valid,10\n"
        ).encode()

        result = await import_transactions(self.db, "invalid-amounts.csv", content)

        self.assertEqual(result.analyzed_rows, 1)
        self.assertEqual(result.invalid_rows, 2)
        self.assertEqual(
            [rejection.reason for rejection in result.rejections],
            ["amount cannot be negative", "amount must be a finite number"],
        )

    async def test_malformed_row_is_counted_as_rejected(self):
        content = (
            "event_type,user_id,amount\n"
            "Transaction,user-a,100\n"
            "Transaction,user-b,not-a-number\n"
        ).encode()

        result = await import_transactions(self.db, "mixed.csv", content)

        self.assertEqual((result.total_rows, result.analyzed_rows, result.rejected_rows), (2, 1, 1))
        self.assertEqual(result.invalid_rows, 1)
        self.assertEqual(result.rejections[0].row, 3)
        self.assertIn("amount must be numeric", result.rejections[0].reason)

    async def test_analysis_failure_rolls_back_all_rows_and_returns_safe_error(self):
        content = (
            "event_type,user_id,amount\n"
            "Transaction,user-a,100\n"
            "Transaction,user-b,200\n"
        ).encode()
        original_analyze = simulator._analyze_and_persist
        calls = 0

        def fail_on_second_row(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("sensitive database detail")
            return original_analyze(*args, **kwargs)

        with patch.object(simulator, "_analyze_and_persist", side_effect=fail_on_second_row):
            with self.assertRaises(CSVImportError) as raised:
                await import_transactions(self.db, "rollback.csv", content)

        self.assertEqual(raised.exception.http_status, 500)
        self.assertNotIn("sensitive database detail", str(raised.exception))
        self.assertEqual(self.db.query(Event).count(), 0)
        self.assertEqual(self.db.query(ModelPrediction).count(), 0)
        self.assertEqual(self.db.query(Alert).count(), 0)
        self.assertEqual(self.db.query(UserRiskProfile).count(), 0)
        self.assertEqual(self.db.query(SimulationStatus).one().events_generated, 12)

    def test_unsupported_columns_are_rejected(self):
        with self.assertRaisesRegex(CSVImportError, "Unsupported CSV columns"):
            parse_transaction_csv("bad.csv", b"customer,txn\nabc,123\n")

    def test_malformed_csv_syntax_is_rejected(self):
        with self.assertRaisesRegex(CSVImportError, "Malformed CSV"):
            parse_transaction_csv(
                "malformed.csv",
                b"event_type,user_id,amount\nTransaction,\"unterminated,10\n",
            )

    def test_large_upload_is_rejected(self):
        with self.assertRaises(CSVImportError) as raised:
            parse_transaction_csv("large.csv", b"x" * (MAX_CSV_BYTES + 1))
        self.assertEqual(raised.exception.http_status, 413)

    def test_maximum_allowed_row_count_is_accepted(self):
        rows = ["event_type,user_id,amount"]
        rows.extend("Transaction,user-a,10" for _ in range(MAX_CSV_ROWS))
        records, rejections, total_rows = parse_transaction_csv(
            "maximum.csv",
            ("\n".join(rows) + "\n").encode(),
        )
        self.assertEqual(total_rows, MAX_CSV_ROWS)
        self.assertEqual(len(records), MAX_CSV_ROWS)
        self.assertEqual(rejections, [])

    def test_rows_over_limit_are_rejected(self):
        rows = ["event_type,user_id,amount"]
        rows.extend("Transaction,user-a,10" for _ in range(MAX_CSV_ROWS + 1))
        with self.assertRaises(CSVImportError) as raised:
            parse_transaction_csv("too-many.csv", ("\n".join(rows) + "\n").encode())
        self.assertEqual(raised.exception.http_status, 413)


class CSVImportEndpointTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine)

        def override_db():
            db = self.session_factory()
            try:
                yield db
            finally:
                db.close()

        from main import app

        self.app = app
        self.app.dependency_overrides[get_db] = override_db

    def tearDown(self):
        self.app.dependency_overrides.clear()
        self.engine.dispose()

    def test_upload_endpoint_returns_import_summary_and_validation_errors(self):
        valid_csv = b"event_type,user_id,amount\nTransaction,api-user,100\n"
        with (
            patch("main.init_db"),
            patch("main.ensure_model"),
            patch("main.SessionLocal", self.session_factory),
            TestClient(self.app) as client,
        ):
            response = client.post(
                "/api/events/import-csv",
                files={"file": ("valid.csv", valid_csv, "text/csv")},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["analyzed_rows"], 1)
            self.assertEqual(response.json()["invalid_rows"], 0)
            self.assertEqual(response.json()["rejected_rows"], 0)
            with self.session_factory() as db:
                self.assertEqual(db.query(ModelPrediction).count(), 1)

            event_list = client.get("/api/events?page_size=50")
            self.assertEqual(event_list.status_code, 200)
            self.assertEqual(event_list.json()["total"], 1)
            self.assertEqual(event_list.json()["items"][0]["user_id"], "api-user")

            dashboard = client.get("/api/dashboard/stats")
            self.assertEqual(dashboard.status_code, 200)
            self.assertEqual(dashboard.json()["total_events"], 1)

            analytics = client.get("/api/analytics/events")
            self.assertEqual(analytics.status_code, 200)
            self.assertEqual(analytics.json()["event_type_distribution"], [{"name": "Transaction", "value": 1}])

            invalid = client.post(
                "/api/events/import-csv",
                files={"file": ("invalid.csv", b"customer,amount\nacct,12\n", "text/csv")},
            )
            self.assertEqual(invalid.status_code, 422)

            oversized = client.post(
                "/api/events/import-csv",
                files={"file": ("large.csv", b"x" * (MAX_CSV_BYTES + 1), "text/csv")},
            )
            self.assertEqual(oversized.status_code, 413)

    def test_analysis_failure_returns_safe_actionable_error(self):
        valid_csv = (
            b"event_type,user_id,amount\n"
            b"Transaction,api-user,100\n"
        )
        with (
            patch("main.init_db"),
            patch("main.ensure_model"),
            patch("main.SessionLocal", self.session_factory),
            patch(
                "services.csv_import_service.simulator._analyze_and_persist",
                side_effect=RuntimeError("sensitive database detail"),
            ),
            TestClient(self.app) as client,
        ):
            response = client.post(
                "/api/events/import-csv",
                files={"file": ("failure.csv", valid_csv, "text/csv")},
            )

        self.assertEqual(response.status_code, 500)
        self.assertIn("No rows were imported", response.json()["detail"])
        self.assertNotIn("sensitive database detail", response.text)
        with self.session_factory() as db:
            self.assertEqual(db.query(Event).count(), 0)
            self.assertEqual(db.query(ModelPrediction).count(), 0)


if __name__ == "__main__":
    unittest.main()
