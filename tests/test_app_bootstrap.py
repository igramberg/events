import unittest

from events.main import create_app


class CreateAppTests(unittest.TestCase):
    def test_create_app_returns_named_fastapi_app(self) -> None:
        app = create_app()

        self.assertEqual("events", app.title)


if __name__ == "__main__":
    unittest.main()
