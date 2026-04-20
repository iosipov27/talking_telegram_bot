from __future__ import annotations

from talking_telegram_bot.models.weather import WeatherResponse


class WeatherReplyFormatterService:
    def format_reply(self, weather: WeatherResponse) -> str:
        lines = [
            f"Погода: {self._format_location(weather)}",
            (
                f"Сейчас: {weather.condition}, {weather.temp_c} °C "
                f"(ощущается как {weather.feels_like_c} °C)"
            ),
            (
                f"Ветер: {weather.wind_direction} {weather.wind_speed_kmph} км/ч, "
                f"влажность {weather.humidity}%, видимость {weather.visibility_km} км"
            ),
        ]
        if weather.forecast:
            lines.append("Ближайший прогноз:")
            for forecast_day in weather.forecast[:3]:
                lines.append(
                    (
                        f"{forecast_day.date}: {forecast_day.condition}, "
                        f"{forecast_day.min_temp_c}..{forecast_day.max_temp_c} °C, "
                        f"восход {forecast_day.sunrise}, закат {forecast_day.sunset}"
                    ),
                )
        return "\n".join(lines)

    def _format_location(self, weather: WeatherResponse) -> str:
        parts = [weather.resolved_location]
        if weather.region:
            parts.append(weather.region)
        if weather.country:
            parts.append(weather.country)
        return ", ".join(parts)

