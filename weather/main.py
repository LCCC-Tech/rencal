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

def weather_data_loop():
    import datetime

    from weather.simulation.weather_data import WeatherData, HistoricalMetadata

    loader = LocalDataLoader()
    manifest_wind = loader.check_historical_weather()
    
    metadata_wind = HistoricalMetadata(
            manifest_wind["basename"], 
            loader.path_resolver_weather_data, 
            datetime.datetime.fromisoformat(manifest_wind["horizon_utc"]["start"]), 
            datetime.datetime.fromisoformat(manifest_wind["horizon_utc"]["end"]), 
            manifest_wind["artifact"]["columns"], 
            manifest_wind["artifact_histogram"]["rows_per_block"])
    
    # Prefix histograms pulled in as memmapped ref:
    prefix_histograms_wind = loader.get_prefix_histograms()
    # Historical data needed at this stage only if desired averages are computed:
    historical_data_wind = loader.get_historical_weather()

    wind_sampler = WeatherData(metadata = metadata_wind,
        desired_averages = {1: [0.34, 0.5, 0.66]},
        prefix_histograms = prefix_histograms_wind,
        historical_data = historical_data_wind)

    print(wind_sampler.random_sample(datetime.datetime(2025, 4, 1), datetime.datetime(2025, 8, 7)).access_col(1, 1))

if __name__ == "__main__":
    weather_data_loop()
