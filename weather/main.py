from weather.core.data_downloader import DownloadManager
from weather.core.data_loader import LocalDataLoader


def main():
    downloader = DownloadManager()
    downloader.download_all()

    loader = LocalDataLoader()
    generation = loader.load_generation_data()


if __name__ == "__main__":
    main()
