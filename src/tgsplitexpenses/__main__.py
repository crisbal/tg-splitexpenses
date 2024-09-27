import logging
from pathlib import Path
import os

from openai import OpenAI

from .tgbot import make_app as tg_make_app
from .config import load_config
from .gsheet import GSheet

logging.basicConfig(level=logging.INFO)
# httpx is verbose
logging.getLogger("httpx").setLevel(logging.WARNING)

if __name__ == "__main__":
    config_file = Path(os.environ.get("TG_SPLITEXPENSE_CONFIG_FILE", "./config.yaml"))
    app_config = load_config(config_file)
    gsheet = GSheet(app_config)
    openai = OpenAI(api_key=app_config.openai.api_key)
    app = tg_make_app(app_config, gsheet, openai)
    logging.info("Running...")
    app.run_polling()
