from fastapi import APIRouter
from app.api.v1 import projects, tasks

api_router = APIRouter()
api_router.include_router(projects.router, prefix="/orgs/{org_slug}/projects", tags=["Projects"])
api_router.include_router(tasks.router, prefix="/orgs/{org_slug}/tasks", tags=["Tasks"])
