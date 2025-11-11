from urllib.parse import urlparse


class ParsedURL:
    """Class for parsing and handling URLs."""

    def __init__(self, raw_url: str):
        self._parsed = urlparse(raw_url)

    @property
    def url(self) -> str:
        """Return the full URL as a string."""
        return self._parsed.geturl()

    @property
    def domain(self) -> str:
        """Return the domain of the URL."""
        return f"{self._parsed.scheme}://{self._parsed.netloc}"
