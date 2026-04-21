import dotenv
import os

dotenv.load_dotenv()

# DEEPSEEK
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_API_URL = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1")
DEEPSEEK_MODEL_CHAT = os.getenv("DEEPSEEK_MODEL_CHAT", "deepseek-chat")
DEEPSEEK_MODEL_REASONER = os.getenv("DEEPSEEK_MODEL_REASONER", "deepseek-reasoner")

# EMBEDDING
EMBEDDING_URL = os.getenv("EMBEDDING_URL", "http://localhost:11434")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "bge-m3")