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
        # Get a list of all files in the directory
        directory = os.path.join(self._base_path, "era5")
        files = os.listdir(self._base_path)

        results = []

        for file in files:
            if file.endswith(".nc"):
                file_path = os.path.join(directory, file)
                data = process_file(file_path, wind_farm_df)
                results.append(data)

        final_results = pd.concat(results, ignore_index=True)

        # Convert datetime to the specified format
        final_results['Times'] = pd.to_datetime(final_results['Times']).dt.tz_localize('UTC').dt.tz_convert('GMT')

        return final_results


