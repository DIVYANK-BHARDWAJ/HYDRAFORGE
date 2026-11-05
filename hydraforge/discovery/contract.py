"""
hydraforge/discovery/contract.py
HYDRAFORGE Standardized Hydrological Inference Contract Specification.
Defines input schema, output schema, serialization formats, missing value rules,
and CLI vs. Python Adapter interface strategies for heterogeneous ML submissions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from hydraforge.schema import (
    CONTRACT_VERSION,
    DEFAULT_NOMINAL_COVERAGE,
    DEFAULT_SUPPORTED_HORIZONS,
    MIN_PERMISSIBLE_DISCHARGE,
    BenchmarkInputRecord,
    PredictionRecord,
)


@dataclass(frozen=True)
class InferenceContractSpecification:
    """Formal definition of the HYDRAFORGE model inference contract."""
    contract_version: str = CONTRACT_VERSION
    supported_horizons: Tuple[int, ...] = DEFAULT_SUPPORTED_HORIZONS
    nominal_interval_coverage: float = DEFAULT_NOMINAL_COVERAGE
    min_permissible_discharge: float = MIN_PERMISSIBLE_DISCHARGE

    # Primary recommended interface: Standardized CLI file-in / file-out
    standard_input_flag: str = "--input"
    standard_output_flag: str = "--output"
    standard_case_flag: str = "--case-id"

    # Supported file serialization formats
    supported_input_formats: Tuple[str, ...] = ("json", "jsonl", "csv", "parquet")
    supported_output_formats: Tuple[str, ...] = ("json", "jsonl")

    # Timestamp format: ISO 8601 UTC
    timestamp_format: str = "ISO8601 (YYYY-MM-DDTHH:MM:SSZ)"

    # Physical units
    discharge_units: str = "m^3/s (or normalized mm/day matching benchmark metadata)"
    temperature_units: str = "degrees Celsius (or Kelvin as specified)"
    precipitation_units: str = "mm/day"

    # Missing value policy
    missing_value_policy: str = (
        "Permitted as null/NaN in historical forcing or past discharge; strictly forbidden "
        "in model predictions. All predicted discharge, probabilities, and intervals must be finite."
    )


def get_sample_input_contract_json() -> Dict[str, Any]:
    """Return canonical example of input record provided to participant model."""
    return {
        "schema_version": CONTRACT_VERSION,
        "case_id": "case_basinshift_2026_001",
        "catchment_id": "catchment_ch_rhone_01",
        "forecast_origin": "2020-05-15T00:00:00Z",
        "horizons": [1, 3, 7],
        "split": "test_a",
        "region": "central_europe",
        "discharge_history": [12.4, 14.1, 13.8, 15.2, 18.0],
        "forcing_history": {
            "total_precipitation": [0.0, 5.2, 14.8, 2.1, 0.0],
            "temperature_2m": [8.5, 9.1, 7.8, 10.2, 11.5],
            "potential_evaporation": [2.1, 1.8, 1.5, 2.4, 2.8]
        },
        "attributes": {
            "drainage_area_km2": 450.5,
            "mean_elevation_m": 1250.0,
            "aridity_index": 0.85
        }
    }


def get_sample_output_contract_json() -> Dict[str, Any]:
    """Return canonical example of output predictions expected from participant model."""
    return {
        "predictions": [
            {
                "case_id": "case_basinshift_2026_001",
                "catchment_id": "catchment_ch_rhone_01",
                "forecast_origin": "2020-05-15T00:00:00Z",
                "horizon": 1,
                "predicted_discharge": 19.45,
                "high_flow_probability": 0.12,
                "extreme_flow_probability": 0.02,
                "prediction_interval_lower": 14.20,
                "prediction_interval_upper": 25.80,
                "nominal_interval_coverage": 0.90
            },
            {
                "case_id": "case_basinshift_2026_001",
                "catchment_id": "catchment_ch_rhone_01",
                "forecast_origin": "2020-05-15T00:00:00Z",
                "horizon": 3,
                "predicted_discharge": 24.10,
                "high_flow_probability": 0.45,
                "extreme_flow_probability": 0.08,
                "prediction_interval_lower": 16.50,
                "prediction_interval_upper": 34.20,
                "nominal_interval_coverage": 0.90
            },
            {
                "case_id": "case_basinshift_2026_001",
                "catchment_id": "catchment_ch_rhone_01",
                "forecast_origin": "2020-05-15T00:00:00Z",
                "horizon": 7,
                "predicted_discharge": 17.80,
                "high_flow_probability": 0.20,
                "extreme_flow_probability": 0.03,
                "prediction_interval_lower": 11.00,
                "prediction_interval_upper": 28.50,
                "nominal_interval_coverage": 0.90
            }
        ]
    }


INTERFACE_ANALYSIS_RATIONALE = """
### HYDRAFORGE Interface Strategy Evaluation: CLI vs. Python Adapter

#### Option A: Standardized CLI Interface (--input <path> --output <path>) [RECOMMENDED]
- **Language & Framework Agnostic**: Participants may use PyTorch, TensorFlow, JAX, XGBoost, LightGBM,
  pure NumPy, scikit-learn, ONNX runtime, C++, Rust, Julia, or R.
- **Dependency Isolation**: Does not pollute the evaluator process memory space or conflict with host library ABIs.
- **Container Sandboxing**: CLI arguments seamlessly map to isolated container mounts:
  `docker run --network none -v /eval/inputs:/inputs:ro -v /eval/outputs:/outputs:rw participant_img python <entrypoint> --input /inputs/cases.json --output /outputs/predictions.json`
- **Fault Containment**: Segmentation faults, memory leaks, or unhandled exceptions in participant code
  terminate only the child process without destabilizing the evaluator engine.
- **Fail-Closed Verification**: The output file is validated strictly after process exit; partial or missing output
  is captured as an evaluable failure without security bypass.

#### Option B: Standardized Python Adapter Interface (e.g. `BaseModel.predict()`)
- **Strengths**: Low latency when invoking thousands of individual benchmark cases sequentially in-memory.
- **Severe Limitations**:
  1. Tightly couples participant Python version and library versions to the host evaluator.
  2. Susceptible to malicious code execution during `import` statements (e.g. `__init__.py` side effects).
  3. Memory leaks and GPU memory fragmentation accumulate across multiple evaluation cases.
  4. Non-Python submissions are completely barred.

#### Recommended Synthesis:
HYDRAFORGE adopts **Option A (CLI file-in / file-out)** as the primary, universal evaluation contract.
For participant projects that only provide an in-memory Python function or class (e.g. `model.predict()`),
HYDRAFORGE generates a zero-dependency, non-invasive CLI adapter shim (`hydraforge_shim.py`) inside the isolated
container at runtime. The participant repository files are NEVER altered or renamed.
"""

