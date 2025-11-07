from weather.core.data_downloader import DownloadManager
from weather.core.data_loader import LocalDataLoader


def main():
    # downloader = DownloadManager()
    # downloader.download_all()
    loader = LocalDataLoader()
    plants = loader.load_wind_plant_data()
    plant_df = plants.to_pandas()
    print(plant_df.head())

if __name__ == "__main__":
    main()
