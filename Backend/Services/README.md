# Backend Services

`Backend/Services` contains runtime configuration, external service clients, and Layer 1 export pipelines.

## Layout

```text
Services/
├── config/
│   ├── env.py
│   └── settings.py
├── clients/
│   └── firebase.py
├── exporters/
│   ├── pipeline.py
│   ├── sources/
│   ├── stores/
│   ├── sync/
│   ├── models/
│   └── utils/
├── dev/
│   ├── env_probe.py
│   └── firebase_services_v2.py
├── .env
└── __init__.py
```

## Responsibilities

### `config/`

Owns environment loading and runtime settings.

- `env.py`: loads `Services/.env` and exposes typed env helpers.
- `settings.py`: defines `ExportSettings` and the default `SETTINGS` instance.

Use:

```python
from Services.config.settings import SETTINGS, ExportSettings
```

### `clients/`

Owns clients for external services.

- `firebase.py`: Firebase RTDB client used by `Backend/main.py` and the exporter pipeline.

Use:

```python
from Services.clients.firebase import FirebaseService
```

### `exporters/`

Owns Layer 1 local artifact export. It reads Firebase or JSON export sources and writes canonical files under `Output_data/Layer1`.

Use:

```python
from Services.exporters import ExportPipeline
```

### `dev/`

Development-only probes or legacy experiments. Code here should not be imported by production pipeline code.

## Environment

Create `Backend/Services/.env` with values such as:

```text
DATABASE_URL=https://<project>.firebaseio.com
FIREBASE_KEY_PATH=path/to/service-account.json
EXPORT_SOURCE=firebase
EXPORT_NODE_ID=Node1
EXPORT_TIMEZONE=Asia/Ho_Chi_Minh
```

Paths in `FIREBASE_KEY_PATH` are resolved relative to `Backend/Services` unless they are absolute.

## Main Entrypoint

Run from repository root:

```powershell
python Backend\main.py --help
```

Run from `Backend`:

```powershell
python main.py --source firebase --node-id Node1 --full-history --skip-layer25
```
