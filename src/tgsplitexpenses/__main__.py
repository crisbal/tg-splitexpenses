import logging
from pathlib import Path
import os

from .tgbot import make_app as tg_make_app
from .config import load_config
from . import models
from .gsheet import GSheet

logging.basicConfig(level=logging.INFO)
# httpx is verbose
logging.getLogger("httpx").setLevel(logging.WARNING)

if __name__ == "__main__":
    config_file = Path(os.environ.get("TG_SPLITEXPENSE_CONFIG_FILE", "./config.yaml"))
    app_config = load_config(Path("./config.yaml"))
    gsheet = GSheet(app_config)
    app = tg_make_app(app_config, gsheet)
    logging.info("Running...")
    app.run_polling()
