from pathlib import Path

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

import app.main as main
from app.core.config import Settings


def test_bundled_frontend_and_api_share_one_origin(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    assets = tmp_path / "assets"
    assets.mkdir()
    (tmp_path / "index.html").write_text("<html>ProcureX app</html>", encoding="utf-8")
    (assets / "app.js").write_text("console.log('app')", encoding="utf-8")
    monkeypatch.setattr(main, "FRONTEND_DIST", tmp_path)
    application = main.create_app(Settings(_env_file=None), readiness_probe=_ready)

    with TestClient(application) as client:
        home = client.get("/")
        assert home.text == "<html>ProcureX app</html>"
        assert "default-src 'self'" in home.headers["content-security-policy"]
        assert client.get("/requisitions/123").text == "<html>ProcureX app</html>"
        assert client.get("/assets/app.js").text == "console.log('app')"
        assert client.get("/api/v1/no-such-route").status_code == 404
        assert client.get("/health/live").json() == {"status": "ok"}


async def _ready() -> None:
    return None
