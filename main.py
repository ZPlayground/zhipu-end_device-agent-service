"""
A2A Agent Service - Main Entry Point
"""
import uvicorn
from src.user_interaction.main_simple import app
from config.settings import settings


def main():
    """启动A2A Agent服务"""
    uvicorn.run(
        "src.user_interaction.main_simple:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )


if __name__ == "__main__":
    main()
