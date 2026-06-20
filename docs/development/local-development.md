# Local Development

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,service]"
pre-commit install
.\scripts\check.ps1
```

`scripts/check.ps1` mirrors CI: ruff, env gates, test standards, HA add-on validation, pytest (97% coverage), and config validate. Use `-Quick` for lint only, `-Fix` to auto-fix ruff issues, `-Integration` when Mosquitto is running locally.

## CLI

```powershell
.\.venv\Scripts\python.exe -m modeldeck config validate --config templates/modeldeck.example.yaml
.\.venv\Scripts\python.exe -m modeldeck collect-once --discovery
.\.venv\Scripts\python.exe -m modeldeck serve
```

## Environment overrides

| Variable | Purpose |
|----------|---------|
| `MODELDECK_CONFIG_DIR` | Config directory (default `/config`) |
| `MODELDECK_DATA_DIR` | Data directory (default `/data`) |
| `MQTT_TEST_HOST` | Mosquitto host for integration tests |

## Integration tests

```powershell
$env:MQTT_TEST_HOST = "localhost"
.\.venv\Scripts\python.exe -m pytest -m integration
```
