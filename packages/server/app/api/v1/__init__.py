from fastapi import APIRouter
from . import projects, tasks, events, channels

api_router = APIRouter()
api_router.include_router(projects.router, prefix="/orgs/{org_slug}/projects", tags=["Projects"])
api_router.include_router(tasks.router, prefix="/orgs/{org_slug}/tasks", tags=["Tasks"])
api_router.include_router(events.router, prefix="/orgs/{org_slug}/events", tags=["Events"])
api_router.include_router(channels.router, prefix="/orgs/{org_slug}/channels", tags=["Channels"])
