"""Abstract base class for the calibration of intermittent generator power curves."""

from abc import ABC, abstractmethod

from ..core.data_loader import DataLoader, LocalDataLoader


class Calibrator(ABC):
    def __init__(
        self,
        data_path: str = None,
        plant_id_col: str = None,
        loader: DataLoader | None = None,
    ):
        """
        Initialise a calibrator instance.

        The Calibrator is an abstract class that specifies the methods any intermittent
        generator's calibration should include, as well as setting up and loading input
        datasets from the configuration file or user-specified paths.

        Args:
            data_path (str): Path to the directory containing the input data files.
            plant_id_col (str): Name of the ID column designating a power plant in the input.
            loader (DataLoader | None): Optional pre-configured data loader. When supplied it
                is used as-is (overriding ``data_path``), allowing inputs to be read from
                non-default locations or sources (e.g. a cloud loader reading directly from
                Blob storage) instead of the default ``LocalDataLoader`` layout.
        """
        if loader is not None:
            self.loader = loader
        else:
            self.loader = LocalDataLoader(data_path) if data_path else LocalDataLoader()
        self.plants = (
            self.loader.load_plant_data(plant_id_col)
            if plant_id_col
            else self.loader.load_plant_data()
        )
        self.generation = (
            self.loader.load_generation_data(plant_id_col)
            if plant_id_col
            else self.loader.load_generation_data()
        )
        self.resource = self.loader.load_era5_data()

    @abstractmethod
    def calibrate(self) -> None:
        """Triggers calibration workflow."""
        pass

    @abstractmethod
    def extract_resource_timeseries_for_plants(self) -> None:
        """Extracts resource time series for plants."""
        pass

    @abstractmethod
    def calculate_historical_load_factors(self) -> None:
        """Calculates historical load factors."""
        pass

    @abstractmethod
    def fit_historical_load_factor_distribution(self) -> None:
        """Fits a distribution to historical load factors."""
        pass

    @abstractmethod
    def estimate_load_factors_for_resource(self) -> None:
        """Estimates load factors based on historical distribution and full resource availability."""
        pass

    @abstractmethod
    def generate_resource_streams(self) -> None:
        """Generates load factor streams for available resource time series for each generator."""
        pass

    @abstractmethod
    def output_historical_load_factor_distribution_parameters(self) -> None:
        """Writes historical load factor parameters to a CSV file."""
        pass

    @abstractmethod
    def output_resource_per_plant(self) -> None:
        """Writes resource time series for each plant to a CSV file."""
        pass

    @abstractmethod
    def output_resource_streams(self) -> None:
        """Writes resource streams to a parquet file."""
        pass

    @abstractmethod
    def output_estimated_load_factors_tabular(self) -> None:
        """Outputs table of estimated load factors."""
        pass

    @abstractmethod
    def output_estimated_load_factors_visual(self) -> None:
        """Outputs a series of plots of estimated load factors and calibrated curves."""
        pass
