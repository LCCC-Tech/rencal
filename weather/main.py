from weather.core.data_downloader import DownloadManager


def main():
    downloader = DownloadManager()
    downloader.download_era5()
    downloader.download_cfd()


if __name__ == "__main__":
    main()
