from weather.core.data_downloader import DownloadManager
from weather.core.data_loader import LocalDataLoader


def main():
    downloader = DownloadManager()
    downloader.download_all()

    loader = LocalDataLoader()
    generation_ds = loader.load_generation_data()
    print(f"Generation data columns {generation_ds.get_columns()}")

if __name__ == "__main__":
    main()
