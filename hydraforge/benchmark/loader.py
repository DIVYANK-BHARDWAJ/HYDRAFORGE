"""Dataset Adapters and Physical Benchmark Loader with Strict Label Shielding."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set
import pandas as pd

from hydraforge.benchmark.validation import DataValidationError, validate_units
from hydraforge.schema import BenchmarkInputRecord, GroundTruthLabel


class BaseDatasetAdapter(ABC):
    """Abstract interface for ingesting diverse raw hydrological datasets."""

    @abstractmethod
    def load_timeseries(self, source_path: Path) -> pd.DataFrame:
        """Load raw streamflow and forcing timeseries into canonical DataFrame."""
        pass

    @abstractmethod
    def load_attributes(self, source_path: Path) -> Dict[str, Dict[str, float]]:
        """Load static catchment attributes."""
        pass


class TabularDatasetAdapter(BaseDatasetAdapter):
    """General CSV / Parquet adapter supporting column remapping and unit verification."""

    def __init__(
        self,
        column_mapping: Optional[Dict[str, str]] = None,
        units_mapping: Optional[Dict[str, str]] = None,
        file_format: str = "csv"
    ) -> None:
        self.column_mapping = column_mapping or {
            "catchment_id": "catchment_id",
            "date": "date",
            "discharge": "discharge",
            "precipitation": "precipitation",
            "temperature": "temperature"
        }
        self.units_mapping = units_mapping or {
            "discharge": "m3/s",
            "precipitation": "mm",
            "temperature": "degC"
        }
        self.file_format = file_format.lower()

    def load_timeseries(self, source_path: Path) -> pd.DataFrame:
        if not source_path.exists():
            raise DataValidationError(f"Source file not found: {source_path}")

        # Validate units first
        for var, u in self.units_mapping.items():
            validate_units(var, u)

        if self.file_format == "parquet":
            df = pd.read_parquet(source_path)
        else:
            df = pd.read_csv(source_path)

        # Invert column mapping to verify presence
        for canon_col, src_col in self.column_mapping.items():
            if src_col not in df.columns:
                raise DataValidationError(f"Expected source column '{src_col}' (for '{canon_col}') not in file.")

        # Standardize DataFrame
        rename_dict = {src: canon for canon, src in self.column_mapping.items()}
        std_df = df.rename(columns=rename_dict)

        # Parse date and sort
        std_df["date"] = pd.to_datetime(std_df["date"])
        std_df = std_df.sort_values(by=["catchment_id", "date"])

        # Duplicate check
        dup_mask = std_df.duplicated(subset=["catchment_id", "date"])
        if dup_mask.any():
            dup_count = int(dup_mask.sum())
            raise DataValidationError(f"Detected {dup_count} duplicate (catchment_id, date) records in dataset.")

        # Check for non-negative discharge where present
        if "discharge" in std_df.columns:
            invalid_q = (std_df["discharge"] < 0) & std_df["discharge"].notna()
            if invalid_q.any():
                raise DataValidationError(f"Detected negative discharge values in source dataset.")

        return std_df

    def load_attributes(self, source_path: Path) -> Dict[str, Dict[str, float]]:
        if not source_path.exists():
            return {}
        if self.file_format == "parquet":
            df = pd.read_parquet(source_path)
        else:
            df = pd.read_csv(source_path)

        if "catchment_id" not in df.columns:
            raise DataValidationError("Attribute table must contain 'catchment_id' column")

        attr_dict: Dict[str, Dict[str, float]] = {}
        for _, row in df.iterrows():
            cid = str(row["catchment_id"])
            feats = {}
            for col in df.columns:
                if col != "catchment_id":
                    val = row[col]
                    if pd.notna(val) and isinstance(val, (int, float)):
                        feats[col] = float(val)
            attr_dict[cid] = feats
        return attr_dict


class CaravanDatasetAdapter(BaseDatasetAdapter):
    """Adapter interface specifically structured for Caravan hydrological dataset standard.

    References:
    - Timeseries stored per data source (e.g., camels, camelsex, hysets).
    - Attributes stored in hydroatlas attributes table.
    """

    def __init__(self, caravan_root_dir: Optional[Path] = None) -> None:
        self.root_dir = Path(caravan_root_dir) if caravan_root_dir else Path("data/caravan")
        self.genuine_files_present = self._check_files_exist()

    def _check_files_exist(self) -> bool:
        if not self.root_dir.exists():
            return False
        # Check for standard Caravan directory markers
        has_timeseries = (self.root_dir / "timeseries").is_dir()
        has_attributes = (self.root_dir / "attributes").is_dir()
        return has_timeseries and has_attributes

    def load_timeseries(self, source_path: Path) -> pd.DataFrame:
        if not self.genuine_files_present:
            raise FileNotFoundError(
                f"Caravan dataset files are not installed at '{self.root_dir}'. "
                "Genuine Caravan files must be staged by organizers before running this adapter."
            )
        # Caravan uses standard netcdf or csv with streamflow in mm/d or m3/s
        raise NotImplementedError("Caravan file reader pending physical dataset staging.")

    def load_attributes(self, source_path: Path) -> Dict[str, Dict[str, float]]:
        if not self.genuine_files_present:
            return {}
        raise NotImplementedError("Caravan attributes reader pending physical dataset staging.")


class ParticipantBenchmarkLoader:
    """Security-isolated loader for participant execution.

    CANNOT read from organizer label storage.
    Only accesses benchmark input directories.
    """

    def __init__(self, base_inputs_dir: Path) -> None:
        self.base_inputs_dir = Path(base_inputs_dir)

    def load_inputs(self, split: str) -> List[BenchmarkInputRecord]:
        split_file = self.base_inputs_dir / split / "inputs.json"
        if not split_file.exists():
            raise FileNotFoundError(f"Input records not found for split '{split}' at '{split_file}'")

        with open(split_file, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        records: List[BenchmarkInputRecord] = []
        for d in raw_data:
            records.append(BenchmarkInputRecord(
                case_id=d["case_id"],
                catchment_id=d["catchment_id"],
                forecast_origin=d["forecast_origin"],
                horizons=list(d["horizons"]),
                discharge_history=list(d.get("discharge_history", [])),
                forcing_history=d.get("forcing_history", {}),
                attributes=d.get("attributes", {}),
                split=d.get("split", split),
                region=d.get("region"),
                is_corrupted=bool(d.get("is_corrupted", False)),
                corruption_family=d.get("corruption_family"),
                clean_case_id=d.get("clean_case_id")
            ))
        return records


class OrganizerBenchmarkLoader:
    """Organizer-only benchmark loader with access to hidden evaluation ground truth."""

    def __init__(self, benchmark_root: Path) -> None:
        self.benchmark_root = Path(benchmark_root)
        self.inputs_dir = self.benchmark_root / "inputs"
        self.labels_dir = self.benchmark_root / "labels"
        self.metadata_dir = self.benchmark_root / "metadata"

    def load_ground_truth(self, split: str) -> List[GroundTruthLabel]:
        label_file = self.labels_dir / split / "labels.json"
        if not label_file.exists():
            raise FileNotFoundError(f"Ground-truth labels not found for split '{split}' at '{label_file}'")

        with open(label_file, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        labels: List[GroundTruthLabel] = []
        for d in raw_data:
            labels.append(GroundTruthLabel(
                case_id=d["case_id"],
                catchment_id=d["catchment_id"],
                forecast_origin=d["forecast_origin"],
                horizon=int(d["horizon"]),
                true_discharge=float(d["true_discharge"]),
                high_flow_threshold=float(d["high_flow_threshold"]),
                extreme_flow_threshold=float(d["extreme_flow_threshold"]),
                persistence_discharge=float(d["persistence_discharge"]) if d.get("persistence_discharge") is not None else None,
                split=d.get("split", split),
                region=d.get("region"),
                is_corrupted=bool(d.get("is_corrupted", False)),
                corruption_family=d.get("corruption_family"),
                clean_case_id=d.get("clean_case_id")
            ))
        return labels

