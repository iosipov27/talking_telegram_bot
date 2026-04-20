from dataclasses import dataclass


@dataclass(frozen=True)
class WeatherForecastDay:
    date: str
    condition: str
    min_temp_c: str
    max_temp_c: str
    min_temp_f: str
    max_temp_f: str
    sunrise: str
    sunset: str


@dataclass(frozen=True)
class WeatherResponse:
    requested_location: str
    resolved_location: str
    region: str
    country: str
    observation_time: str
    condition: str
    temp_c: str
    temp_f: str
    feels_like_c: str
    feels_like_f: str
    humidity: str
    wind_speed_kmph: str
    wind_speed_miles: str
    wind_direction: str
    visibility_km: str
    forecast: list[WeatherForecastDay]

