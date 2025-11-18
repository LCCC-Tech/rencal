from weather.core.data_downloader import DownloadManager
from weather.core.data_loader import LocalDataLoader
from weather.utils.logger import get_logger

logger = get_logger(__name__)


def main():
    downloader = DownloadManager()
    downloader.download_all()

    loader = LocalDataLoader()
    plant_ds = loader.load_plant_data()
    wind_plant_ds = plant_ds.get_wind_plants()
    logger.info(wind_plant_ds)

    generation_ds = loader.load_generation_data()
    logger.info(generation_ds)

    weather_ds = loader.load_era5_data()
    logger.info(weather_ds)


if __name__ == "__main__":
    main()
