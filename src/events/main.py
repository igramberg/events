from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="events")

    @app.get("/")
    async def root() -> dict[str, str]:
        return {"status": "bootstrap"}

    return app


app = create_app()
