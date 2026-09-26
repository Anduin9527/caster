from urllib.parse import urlsplit

import uvicorn
from _config import CONFIG

if __name__ == "__main__":
    url = urlsplit(CONFIG["AIGC_API_URL"])
    uvicorn.run("aigc.api:app", host=url.hostname or "127.0.0.1", port=url.port or 8189, workers=1)
