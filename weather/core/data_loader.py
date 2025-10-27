import os
from abc import ABC, abstractmethod

import pandas as pd


class DataLoader(ABC):
    @property
    @abstractmethod
    def base_path(self) -> str:
        pass

    @abstractmethod
    def load_era5_data(self) -> pd.DataFrame:
        pass

    @abstractmethod
    def load_metered_generation_data(self) -> pd.DataFrame:
        pass

    @abstractmethod
    def load_cfd_mapping_data(self) -> pd.DataFrame:
        pass


class LocalDataLoader(DataLoader):
    def __init__(self):
        self._base_path: str = "./data"

    @property
    def base_path(self) -> str:
        return self._base_path

    @base_path.setter
    def base_path(self, path: str):
        self._base_path = path

    def load_era5_data(self) -> pd.DataFrame:
        pass
