import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aigc.config import load

CONFIG = load()
API_URL = CONFIG["AIGC_API_URL"].rstrip("/")
COMFY_URL = CONFIG["AIGC_COMFY_URL"].rstrip("/")
DATA_DIR = Path(CONFIG["AIGC_DATA_DIR"])
