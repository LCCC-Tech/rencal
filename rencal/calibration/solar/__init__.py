from pathlib import Path


def __init__(self, config):
    self.config = config
    self.output_path = Path(config["output_path"])

    self.output_path.mkdir(parents=True, exist_ok=True)
