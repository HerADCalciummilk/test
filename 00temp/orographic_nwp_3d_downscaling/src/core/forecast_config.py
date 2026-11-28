"""Read per-model forecast-hour bounds without meteorological dependencies."""


def forecast_hour_range(config, model_region, forecast_hours):
    hours = list(forecast_hours)
    if not hours:
        raise ValueError("Model forecast-hour list is empty")
    section = "ForecastHourRange"
    # Older configurations without bounds use the complete model hour list.
    if not config.has_option(section, model_region):
        begin, end = min(hours), max(hours)
    else:
        raw = config.get(section, model_region)
        try:
            begin, end = [int(value.strip()) for value in raw.split(",")]
        except ValueError as exc:
            raise ValueError(
                f"[{section}] {model_region} must be two integer hours: begin,end"
            ) from exc
    if begin < 0 or end < begin:
        raise ValueError(f"[{section}] {model_region}: require 0 <= begin <= end")
    if not any(begin <= hour <= end for hour in hours):
        raise ValueError(
            f"[{section}] {model_region}: range {begin}-{end} contains no model forecast hours"
        )
    return begin, end
