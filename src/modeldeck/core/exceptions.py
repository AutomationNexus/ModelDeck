"""Application exceptions."""


class ModelDeckError(Exception):
    """Base error for ModelDeck."""


class ConfigError(ModelDeckError):
    """Invalid or missing configuration."""


class CollectorError(ModelDeckError):
    """Collector execution failed."""


class MqttError(ModelDeckError):
    """MQTT publish or connect failed."""
