import os
from datetime import UTC, datetime, timedelta

from dotenv import load_dotenv

from curator.weather import get_historical_weather


def main():
    weather = get_historical_weather(
        os.getenv("WEATHER_API_KEY"), "80027", datetime.now(UTC) - timedelta(hours=24)
    )
    print(weather)


if __name__ == "__main__":
    load_dotenv()
    main()
