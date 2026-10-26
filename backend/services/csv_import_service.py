"""Validation and analysis of imported transaction CSV files."""

from __future__ import annotations

import csv
import io
import logging
import math
from datetime import datetime, timezone
from typing import Any

from fastapi import status
from sqlalchemy.orm import Session

from models import Settings as AppSettings, SimulationStatus
from schemas import CSVImportResponse
from services.alert_service import alert_to_dict, create_alert_from_event
from services.event_simulator import simulator
from services.websocket_manager import manager
from utils.risk_utils import EVENT_TYPES

MAX_CSV_BYTES = 10 * 1024 * 1024
MAX_CSV_ROWS = 50000
MAX_REJECTIONS_IN_RESPONSE = 100
PAYSIM_REQUIRED_COLUMNS = {"type", "amount", "nameorig"}
GENERIC_REQUIRED_COLUMNS = {"event_type", "user_id", "amount"}
PAYSIM_TYPES = {
    "CASH_IN": "Transaction",
    "CASH_OUT": "Transaction",
    "DEBIT": "Transaction",
    "PAYMENT": "Payment",
    "TRANSFER": "Transaction",
}
GENERIC_EVENT_TYPE_ALIASES = {
    "transfer": "Transaction",
    "withdrawal": "Transaction",
    "purchase": "Transaction",
}
CANONICAL_EVENT_TYPES = {event_type.casefold(): event_type for event_type in EVENT_TYPES}
FRAUD_LABEL_COLUMNS = ("isfraud", "is_fraud", "fraud")
logger = logging.getLogger(__name__)


class CSVImportError(ValueError):
    def __init__(self, detail: str, http_status: int = status.HTTP_422_UNPROCESSABLE_ENTITY):
        super().__init__(detail)
        self.http_status = http_status


def _number(value: str, field: str, *, integer: bool = False) -> float | int:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} must be a finite number")
    if number < 0:
        raise ValueError(f"{field} cannot be negative")
    if integer:
        if not number.is_integer():
            raise ValueError(f"{field} must be a whole number")
        return int(number)
    return number


def _timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamp must be an ISO-8601 date and time") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _validate_row(
    row: dict[str | None, str | None],
    source_format: str,
    headers: set[str],
) -> dict[str, Any]:
    if None in row:
        raise ValueError("row has more fields than the CSV header")
    values = {
        key: value.strip() if value is not None else ""
        for key, value in row.items()
        if key is not None
    }

    label_column = next((name for name in FRAUD_LABEL_COLUMNS if name in headers), None)
    label = None
    if label_column:
        label_value = values[label_column]
        if label_value not in {"0", "1"}:
            raise ValueError(f"{label_column} must be 0 or 1")
        label = label_value == "1"
    flagged = None
    if "isflaggedfraud" in headers:
        flagged_value = values["isflaggedfraud"]
        if flagged_value not in {"0", "1"}:
            raise ValueError("isFlaggedFraud must be 0 or 1")
        flagged = flagged_value == "1"

    amount = _number(values["amount"], "amount")
    if source_format == "paysim":
        transaction_type = values["type"].upper()
        if transaction_type not in PAYSIM_TYPES:
            raise ValueError(f"unsupported PaySim transaction type: {values['type']}")
        user_id = values["nameorig"]
        event_type = PAYSIM_TYPES[transaction_type]
        timestamp = datetime.now(timezone.utc).replace(tzinfo=None)
        metadata: dict[str, Any] = {"source_format": "PaySim"}
        if "step" in headers:
            metadata["paysim_step"] = _number(values["step"], "step", integer=True)
        balance_fields = {
            "oldbalanceorg": "origin_balance_before",
            "newbalanceorig": "origin_balance_after",
            "oldbalancedest": "destination_balance_before",
            "newbalancedest": "destination_balance_after",
        }
        for column, key in balance_fields.items():
            if column in headers:
                metadata[key] = _number(values[column], column)
        if "namedest" in headers:
            metadata["destination_id"] = values["namedest"] or None
    else:
        source_event_type = values["event_type"]
        if not source_event_type:
            raise ValueError("event_type is required")
        event_type_key = source_event_type.casefold()
        event_type = CANONICAL_EVENT_TYPES.get(event_type_key)
        if event_type is None:
            event_type = GENERIC_EVENT_TYPE_ALIASES.get(event_type_key)
        if event_type is None:
            raise ValueError(
                f"unsupported event_type: {source_event_type}. Use an application event type "
                "or one of Payment, Transaction, Transfer, Withdrawal, Purchase."
            )
        user_id = values["user_id"]
        timestamp = _timestamp(values["timestamp"]) if "timestamp" in headers else datetime.now(timezone.utc).replace(tzinfo=None)
        metadata = {"source_format": "Risk Radar CSV"}
        if source_event_type != event_type:
            metadata["source_event_type"] = source_event_type

    if not user_id or len(user_id) > 64:
        raise ValueError("user identifier is required and must be 64 characters or fewer")
    if len(event_type) > 50:
        raise ValueError("event_type must be 50 characters or fewer")
    if source_format == "generic":
        status_value = values.get("status") or "success"
        ip_address = values.get("ip_address") or None
        location = values.get("location") or None
        device = values.get("device") or None
        for name, value, limit in (
            ("status", status_value, 50),
            ("ip_address", ip_address, 64),
            ("location", location, 120),
            ("device", device, 120),
        ):
            if value is not None and len(value) > limit:
                raise ValueError(f"{name} exceeds the maximum length of {limit}")
    else:
        status_value = "success"
        ip_address = None
        location = "PaySim"
        device = "CSV import"

    return {
        "event_type": event_type,
        "user_id": user_id,
        "ip_address": ip_address,
        "location": location,
        "device": device,
        "amount": amount,
        "status": status_value,
        "timestamp": timestamp,
        "metadata_json": metadata,
        "_dataset_label_is_fraud": label,
        "_dataset_flagged_fraud": flagged,
    }


def parse_transaction_csv(filename: str, content: bytes) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    if not filename.lower().endswith(".csv"):
        raise CSVImportError("Upload a .csv file.")
    if len(content) > MAX_CSV_BYTES:
        raise CSVImportError(
            f"CSV file exceeds the {MAX_CSV_BYTES // (1024 * 1024)} MB upload limit.",
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CSVImportError("CSV must use UTF-8 text encoding.") from exc
    if not text.strip():
        raise CSVImportError("CSV file is empty.")

    stream = io.StringIO(text, newline="")
    reader = csv.DictReader(stream, strict=True)
    if not reader.fieldnames:
        raise CSVImportError("CSV header row is missing.")
    headers_list = [header.strip().lower() for header in reader.fieldnames if header is not None]
    if len(headers_list) != len(reader.fieldnames) or any(not header for header in headers_list):
        raise CSVImportError("CSV contains an empty column name.")
    if len(set(headers_list)) != len(headers_list):
        raise CSVImportError("CSV contains duplicate column names.")
    reader.fieldnames = headers_list
    headers = set(headers_list)
    if PAYSIM_REQUIRED_COLUMNS.issubset(headers):
        source_format = "paysim"
    elif GENERIC_REQUIRED_COLUMNS.issubset(headers):
        source_format = "generic"
    else:
        raise CSVImportError(
            "Unsupported CSV columns. Provide PaySim columns (type, amount, nameOrig) "
            "or Risk Radar columns (event_type, user_id, amount)."
        )

    records: list[dict[str, Any]] = []
    rejections: list[dict[str, Any]] = []
    total_rows = 0
    try:
        for row_number, row in enumerate(reader, start=2):
            if all(value is None or not value.strip() for value in row.values()):
                continue
            total_rows += 1
            if total_rows > MAX_CSV_ROWS:
                raise CSVImportError(
                    f"CSV exceeds the {MAX_CSV_ROWS} data-row limit.",
                    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                )
            try:
                validated = _validate_row(row, source_format, headers)
                validated["_source_row"] = row_number
                records.append(validated)
            except ValueError as exc:
                rejections.append({"row": row_number, "reason": str(exc)})
    except csv.Error as exc:
        raise CSVImportError(f"Malformed CSV near line {reader.line_num}: {exc}") from exc

    if total_rows == 0:
        raise CSVImportError("CSV contains no transaction rows.")
    return records, rejections, total_rows


async def import_transactions(db: Session, filename: str, content: bytes) -> CSVImportResponse:
    records, rejections, total_rows = parse_transaction_csv(filename, content)
    analyzed_rows = 0
    detected_anomalies = 0
    broadcasts: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
    row_number = 0
    try:
        status_row = db.query(SimulationStatus).first()
        if not status_row:
            status_row = SimulationStatus(is_running=False)
            db.add(status_row)
            db.flush()
        settings = db.query(AppSettings).first()

        for raw in records:
            row_number = raw.pop("_source_row")
            dataset_label = raw.pop("_dataset_label_is_fraud")
            flagged_label = raw.pop("_dataset_flagged_fraud")
            event = simulator._analyze_and_persist(
                db,
                raw,
                status_row,
                settings,
                count_as_simulation=False,
                commit=False,
            )
            event.metadata_json = {
                **(event.metadata_json or {}),
                "import": {
                    "source": "csv",
                    "dataset_label_is_fraud": dataset_label,
                    "dataset_flagged_fraud": flagged_label,
                },
            }
            alert = create_alert_from_event(
                db,
                event,
                {
                    "risk_score": event.risk_score,
                    "risk_level": event.risk_level,
                    "risk_factors": event.risk_factors or [],
                    "recommended_action": event.recommended_action,
                },
                commit=False,
            )
            event_payload = simulator._event_to_dict(event)
            alert_payload = (
                alert_to_dict(alert)
                if alert and alert.status == "Open"
                else None
            )
            broadcasts.append((event_payload, alert_payload))
            analyzed_rows += 1
            detected_anomalies += int(event.is_anomaly)

        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("CSV import transaction failed on row %s", row_number or "initialization")
        raise CSVImportError(
            "CSV import could not be completed during analysis or storage. "
            "No rows were imported; please retry. If the problem continues, contact support.",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ) from exc

    for event_payload, alert_payload in broadcasts:
        await manager.broadcast_event(event_payload)
        if alert_payload:
            await manager.broadcast_alert(alert_payload)
        await manager.broadcast_stats_hint()

    return CSVImportResponse(
        total_rows=total_rows,
        analyzed_rows=analyzed_rows,
        invalid_rows=len(rejections),
        rejected_rows=len(rejections),
        detected_anomalies=detected_anomalies,
        rejections=rejections[:MAX_REJECTIONS_IN_RESPONSE],
        rejections_truncated=max(0, len(rejections) - MAX_REJECTIONS_IN_RESPONSE),
    )
