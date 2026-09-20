from fastapi import APIRouter
from .controllers import users
from .controllers import appointments
from .controllers import therapists
from .controllers import reviews
from .controllers import roles
from .controllers import images
from .controllers import applications
from .controllers import articles
from .controllers import news
from .controllers import psychologist_statuses

api_router = APIRouter()
api_router.include_router(users.router)
api_router.include_router(appointments.router)
api_router.include_router(reviews.router)
api_router.include_router(roles.router)
api_router.include_router(therapists.router)
api_router.include_router(images.router)
api_router.include_router(applications.router)
api_router.include_router(articles.router)
api_router.include_router(news.router)
api_router.include_router(psychologist_statuses.router)