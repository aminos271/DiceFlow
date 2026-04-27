import dotenv
import os

dotenv.load_dotenv()

# DEEPSEEK
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_API_URL = os.getenv("DEEPSEEK_API_URL") or os.getenv("DEEPSEEK_API_BASE_URL") or "https://api.deepseek.com/v1"
DEEPSEEK_MODEL_FLASH = os.getenv("DEEPSEEK_MODEL_FLASH", "deepseek-v4-flash")
DEEPSEEK_MODEL_PRO = os.getenv("DEEPSEEK_MODEL_PRO", "deepseek-v4-pro")
# Legacy alias — prefer DEEPSEEK_MODEL_PRO for new code
DEEPSEEK_MODEL_CHAT = os.getenv("DEEPSEEK_MODEL_CHAT") or DEEPSEEK_MODEL_PRO

# EMBEDDING
EMBEDDING_URL = os.getenv("EMBEDDING_URL", "http://localhost:11434")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "bge-m3")