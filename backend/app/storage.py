import json
import sqlite3
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any


class DetectionStore:
    def __init__(self, database_path: Path, uploads_path: Path):
        self.database_path = database_path
        self.uploads_path = uploads_path

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.uploads_path.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS detections (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    crop_name TEXT,
                    disease_name TEXT NOT NULL,
                    classification TEXT NOT NULL,
                    prediction_score REAL,
                    created_at TEXT NOT NULL,
                    latitude REAL,
                    longitude REAL,
                    gps_fix_valid INTEGER,
                    gps_timestamp TEXT,
                    captured_at TEXT,
                    model_name TEXT,
                    model_version TEXT,
                    top_predictions TEXT NOT NULL
                )
                """
            )
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(detections)")}
            for column, definition in (
                ("gps_fix_valid", "INTEGER"),
                ("gps_timestamp", "TEXT"),
                ("captured_at", "TEXT"),
            ):
                if column not in columns:
                    connection.execute(f"ALTER TABLE detections ADD COLUMN {column} {definition}")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_detections_created_at ON detections(created_at)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_detections_crop ON detections(crop_name)")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def create(self, record: dict[str, Any]) -> dict[str, Any]:
        stored = {**record, "created_at": datetime.now(timezone.utc).isoformat()}
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO detections
                (id, filename, crop_name, disease_name, classification, prediction_score,
                 created_at, latitude, longitude, gps_fix_valid, gps_timestamp, captured_at,
                 model_name, model_version, top_predictions)
                VALUES (:id, :filename, :crop_name, :disease_name, :classification, :prediction_score,
                 :created_at, :latitude, :longitude, :gps_fix_valid, :gps_timestamp, :captured_at,
                 :model_name, :model_version, :top_predictions)""",
                {
                    **stored,
                    "top_predictions": json.dumps(record.get("top_predictions", [])),
                },
            )
        return self._serialize(stored)

    def list(
        self,
        page: int = 1,
        page_size: int = 20,
        crop: str | None = None,
        disease: str | None = None,
        search: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        locations_only: bool = False,
    ) -> dict[str, Any]:
        clauses: list[str] = []
        values: list[Any] = []
        for column, value in (("crop_name", crop), ("disease_name", disease)):
            if value:
                clauses.append(f"LOWER({column}) LIKE ?")
                values.append(f"%{value.strip().lower()}%")
        if search:
            clauses.append("(LOWER(COALESCE(crop_name, '')) LIKE ? OR LOWER(disease_name) LIKE ?)")
            values.extend([f"%{search.strip().lower()}%", f"%{search.strip().lower()}%"])
        if from_date:
            clauses.append("created_at >= ?")
            values.append(datetime.combine(from_date, time.min, timezone.utc).isoformat())
        if to_date:
            clauses.append("created_at < ?")
            values.append((datetime.combine(to_date + timedelta(days=1), time.min, timezone.utc)).isoformat())
        if locations_only:
            clauses.append("latitude IS NOT NULL AND longitude IS NOT NULL")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            total = connection.execute(f"SELECT COUNT(*) FROM detections {where}", values).fetchone()[0]
            rows = connection.execute(
                f"SELECT * FROM detections {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                [*values, page_size, (page - 1) * page_size],
            ).fetchall()
        pages = (total + page_size - 1) // page_size
        return {
            "items": [self._serialize(dict(row)) for row in rows],
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": pages,
        }

    def get(self, detection_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM detections WHERE id = ?", (detection_id,)).fetchone()
        return self._serialize(dict(row)) if row else None

    def stats(self) -> dict[str, Any]:
        with self._connect() as connection:
            total = connection.execute("SELECT COUNT(*) FROM detections").fetchone()[0]
            categories = connection.execute(
                "SELECT classification, COUNT(*) AS count FROM detections GROUP BY classification"
            ).fetchall()
            geolocated = connection.execute(
                "SELECT COUNT(*) FROM detections WHERE latitude IS NOT NULL AND longitude IS NOT NULL"
            ).fetchone()[0]
            crops = connection.execute(
                "SELECT COALESCE(crop_name, 'Unknown') AS crop_name, COUNT(*) AS count "
                "FROM detections GROUP BY crop_name ORDER BY count DESC"
            ).fetchall()
            diseases = connection.execute(
                "SELECT COALESCE(crop_name, 'Unknown') AS crop_name, disease_name, COUNT(*) AS count "
                "FROM detections WHERE classification = 'diseased' "
                "GROUP BY crop_name, disease_name ORDER BY count DESC LIMIT 10"
            ).fetchall()
            since = (datetime.now(timezone.utc) - timedelta(days=13)).date().isoformat()
            activity = connection.execute(
                "SELECT substr(created_at, 1, 10) AS date, COUNT(*) AS count FROM detections "
                "WHERE created_at >= ? GROUP BY substr(created_at, 1, 10)",
                (since,),
            ).fetchall()
        counts = {row["classification"]: row["count"] for row in categories}
        total_crops = sum(row["count"] for row in crops)
        activity_by_date = {row["date"]: row["count"] for row in activity}
        start = (datetime.now(timezone.utc) - timedelta(days=13)).date()
        days = [
            {"date": (start + timedelta(days=offset)).strftime("%b %d"), "count": activity_by_date.get((start + timedelta(days=offset)).isoformat(), 0)}
            for offset in range(14)
        ]
        return {
            "total_images": total,
            "diseased_images": counts.get("diseased", 0),
            "healthy_images": counts.get("healthy", 0),
            "inconclusive_images": counts.get("inconclusive", 0),
            "geolocated_images": geolocated,
            "crop_distribution": [
                {"crop_name": row["crop_name"], "count": row["count"], "percentage": round(100 * row["count"] / total_crops, 1)}
                for row in crops
            ],
            "disease_distribution": [
                {"crop_name": row["crop_name"], "disease_name": row["disease_name"], "count": row["count"]}
                for row in diseases
            ],
            "activity": days,
        }

    def _serialize(self, row: dict[str, Any]) -> dict[str, Any]:
        top_predictions = row.get("top_predictions", "[]")
        if isinstance(top_predictions, str):
            top_predictions = json.loads(top_predictions)
        return {
            "id": row["id"],
            "image_url": f"/api/images/{row['filename']}",
            "crop_name": row["crop_name"],
            "disease_name": row["disease_name"],
            "classification": row["classification"],
            "prediction_score": row["prediction_score"],
            "created_at": row["created_at"],
            "latitude": row["latitude"],
            "longitude": row["longitude"],
            "gps_fix_valid": bool(row["gps_fix_valid"]) if row["gps_fix_valid"] is not None else None,
            "gps_timestamp": row["gps_timestamp"],
            "captured_at": row["captured_at"],
            "model_name": row["model_name"],
            "model_version": row["model_version"],
            "top_predictions": top_predictions,
        }
