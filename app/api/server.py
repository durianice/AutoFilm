from fastapi import FastAPI
from app.core import settings
from app.api.routes import router
from app.api.webhooks import router as webhooks_router
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AutoFilm API 服务"
)

app.include_router(router)
app.include_router(webhooks_router)