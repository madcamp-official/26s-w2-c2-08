"""Local development server entry point."""

import uvicorn

from tbd.config import get_settings


def main() -> None:
    """Run Uvicorn with values from the shared repository environment."""

    settings = get_settings()
    uvicorn.run(
        "tbd.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_env == "development",
    )


if __name__ == "__main__":
    main()
