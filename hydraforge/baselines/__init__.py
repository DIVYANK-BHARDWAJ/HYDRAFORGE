"""HYDRAFORGE Reference Baselines Subpackage.

Provides standard benchmark reference models:
- PersistenceBaseline (Last known observation)
- ClimatologyBaseline (Day-of-year historical mean)
- GBDTBaseline (XGBoost lagged regressor)
"""

from hydraforge.baselines.persistence import PersistenceBaseline
from hydraforge.baselines.climatology import ClimatologyBaseline
from hydraforge.baselines.gbdt import GBDTBaseline

__all__ = [
    "PersistenceBaseline",
    "ClimatologyBaseline",
    "GBDTBaseline",
]

