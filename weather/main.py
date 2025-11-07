from weather.core.data_downloader import DownloadManager


def main():
    downloader = DownloadManager()
    downloader.download_all()

if __name__ == "__main__":
    main()
