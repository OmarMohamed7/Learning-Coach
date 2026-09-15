
from dotenv import load_dotenv
from logger import get_logger
from src.config import settings

load_dotenv()

logger = get_logger(__name__)

def main():
    logger.info("Hello from Learning Coach!")
    logger.info("Ollama base URL: %s", settings.ollama_base_url)


if __name__ == "__main__":
    main()
