# Contributing

## Development setup

1. Install Python 3.12 or newer.
2. Run the platform installer or create a virtual environment manually.
3. Install dependencies:

```bash
python -m pip install -r requirements.txt
```

4. Copy `.env.example` to `.env` and configure the required credentials.
5. Start the application with `python app.py`.

## Before opening a pull request

- Keep secrets and credentials out of the repository.
- Run the application and verify the main extraction flow.
- Run the repository checks:

```bash
python -m compileall -q app.py
```

- Keep commit messages concise and descriptive.
- Update the README when changing installation, configuration or user-facing behaviour.
