from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHAT_HISTORY_DIR_PATH = PROJECT_ROOT / "logs"
LOG_FILE_PATH = PROJECT_ROOT / "logs" / "bot.log"
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
LOG_MAX_BYTES = 1_000_000
LOG_BACKUP_COUNT = 5
