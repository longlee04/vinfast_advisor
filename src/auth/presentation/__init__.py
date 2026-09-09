"""FastAPI presentation adapters for Auth."""

from src.auth.presentation.admin_routes import router as admin_router
from src.auth.presentation.routes import router
from src.auth.presentation.staff_routes import router as staff_router

__all__ = ["router", "staff_router", "admin_router"]
