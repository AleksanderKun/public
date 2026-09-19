from fastapi import FastAPI
from .conversation_routes import router
from .config import Config

app = FastAPI()

app.include_router(router)

if __name__ == "__main__":
    import uvicorn

    config = Config()
    uvicorn.run(app, host="0.0.0.0", port=8000)
