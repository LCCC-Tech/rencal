from weather.core.data_downloader import DownloadManager


def main():
    downloader = DownloadManager()
    downloader.download_cfd()
    downloader.download_generation_data()
    downloader.download_era5()


if __name__ == "__main__":
    main()
