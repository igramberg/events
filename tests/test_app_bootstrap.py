import inspect
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import events.main as main_module
from events.main import create_app


class CreateAppTests(unittest.TestCase):
    def test_create_app_returns_named_fastapi_app(self) -> None:
        app = create_app()

        self.assertEqual("events", app.title)

    def test_root_route_is_synchronous(self) -> None:
        app = create_app()
        root_route = next(
            route for route in app.routes if getattr(route, "path", None) == "/"
        )

        self.assertFalse(inspect.iscoroutinefunction(root_route.endpoint))

    def test_default_database_url_uses_env_override(self) -> None:
        with patch.dict(
            os.environ,
            {"EVENTS_DATABASE_URL": "sqlite+pysqlite:////tmp/events-test.db"},
            clear=False,
        ):
            self.assertEqual(
                "sqlite+pysqlite:////tmp/events-test.db",
                main_module._default_database_url(),
            )

    def test_default_database_url_uses_user_data_location(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            if main_module.sys.platform == "darwin":
                expected_path = (
                    Path.home()
                    / "Library"
                    / "Application Support"
                    / "events"
                    / "events.db"
                )
            elif main_module.sys.platform == "win32":
                expected_path = (
                    Path(
                        os.environ.get(
                            "APPDATA",
                            Path.home() / "AppData" / "Roaming",
                        )
                    )
                    / "events"
                    / "events.db"
                )
            else:
                expected_path = (
                    Path(
                        os.environ.get(
                            "XDG_STATE_HOME",
                            Path.home() / ".local" / "state",
                        )
                    )
                    / "events"
                    / "events.db"
                )

            self.assertEqual(
                f"sqlite+pysqlite:///{expected_path}",
                main_module._default_database_url(),
            )

    def test_default_database_path_handles_platform_specific_defaults(self) -> None:
        with patch.object(main_module.sys, "platform", "darwin"):
            self.assertEqual(
                Path.home()
                / "Library"
                / "Application Support"
                / "events"
                / "events.db",
                main_module._default_database_path(),
            )

        with patch.object(main_module.sys, "platform", "win32"):
            with patch.dict(
                os.environ,
                {"APPDATA": "/tmp/appdata"},
                clear=False,
            ):
                self.assertEqual(
                    Path("/tmp/appdata/events/events.db"),
                    main_module._default_database_path(),
                )

        with patch.object(main_module.sys, "platform", "linux"):
            with patch.dict(
                os.environ,
                {"XDG_STATE_HOME": "/tmp/state-home"},
                clear=False,
            ):
                self.assertEqual(
                    Path("/tmp/state-home/events/events.db"),
                    main_module._default_database_path(),
                )

    def test_default_database_url_uses_forward_slashes_on_windows(self) -> None:
        with patch.object(main_module.sys, "platform", "win32"):
            with patch.dict(
                os.environ,
                {"APPDATA": r"C:\Users\me\AppData\Roaming"},
                clear=True,
            ):
                self.assertEqual(
                    "sqlite+pysqlite:///C:/Users/me/AppData/Roaming/events/events.db",
                    main_module._default_database_url(),
                )

    def test_ensure_sqlite_parent_dir_supports_multiple_sqlite_url_prefixes(
        self,
    ) -> None:
        with TemporaryDirectory() as temp_dir:
            sqlite_parent = Path(temp_dir) / "sqlite" / "nested"
            pysqlite_parent = Path(temp_dir) / "pysqlite" / "nested"

            main_module._ensure_sqlite_parent_dir(
                f"sqlite:///{sqlite_parent / 'events.db'}"
            )
            main_module._ensure_sqlite_parent_dir(
                f"sqlite+pysqlite:///{pysqlite_parent / 'events.db'}"
            )

            self.assertTrue(sqlite_parent.is_dir())
            self.assertTrue(pysqlite_parent.is_dir())


if __name__ == "__main__":
    unittest.main()
