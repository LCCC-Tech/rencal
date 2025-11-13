from weather.core.data_downloader import DownloadManager
from weather.core.data_loader import LocalDataLoader
from weather.utils.logger import get_logger

logger = get_logger(__name__)


def main():
    downloader = DownloadManager()
    downloader.download_all()

    loader = LocalDataLoader()
    plant_ds = loader.load_wind_plant_data()
    logger.info(f"Plant data columns {plant_ds.get_columns()}")

    generation_ds = loader.load_generation_data()
    logger.info(f"Generation data columns {generation_ds.get_columns()}")

    weather_ds = loader.load_era5_data()
    logger.info(f"Weather data columns {weather_ds.get_columns()}")


if __name__ == "__main__":
    main()
