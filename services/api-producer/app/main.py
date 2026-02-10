from fastapi import FastAPI
from app.api.ingest import router as ingest_router

# create the FastAPI application
app = FastAPI(title="EventFlow API Producer")

# register routers
app.include_router(ingest_router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok"}
