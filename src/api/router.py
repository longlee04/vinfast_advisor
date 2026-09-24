"""Central aggregation boundary for application API routes."""

from fastapi import APIRouter

from src.agents.api.admin_assignment_routes import (
    router as admin_assignment_router,
)
from src.agents.api.advisor_routes import router as agents_advisor_router
from src.agents.api.analytics_routes import router as agents_analytics_router
from src.agents.api.booking_routes import router as agents_booking_router
from src.agents.api.bottleneck_signal_routes import router as agents_bottleneck_signal_router
from src.agents.api.conversation_routes import router as agents_conversation_router
from src.agents.api.customer_360_routes import admin_router as agents_customer_360_admin_router
from src.agents.api.customer_360_routes import advisor_router as agents_customer_360_advisor_router
from src.agents.api.customer_360_routes import meta_router as agents_customer_360_meta_router
from src.agents.api.customer_routes import router as agents_customer_router
from src.agents.api.history_routes import router as agents_history_router
from src.agents.api.memory_routes import router as agents_memory_router
from src.agents.api.nearby_location_routes import (
    legacy_router as legacy_nearby_location_router,
)
from src.agents.api.nearby_location_routes import (
    router as nearby_location_router,
)
from src.agents.api.notice_routes import router as agents_notice_router
from src.agents.api.review_routes import reviews_router as agents_reviews_router
from src.agents.api.review_routes import router as agents_review_router
from src.agents.api.routes import router as agents_router
from src.agents.api.sales_opportunity_routes import router as agents_sales_opportunity_router
from src.agents.api.test_drive_routes import router as agents_test_drive_router
from src.agents.api.turn_trace_routes import router as agents_turn_trace_router
from src.auth.presentation import admin_router, staff_router
from src.auth.presentation import router as auth_router
from src.document.presentation.admin_routes import router as document_admin_router
from src.document.presentation.policy_routes import router as policy_notification_router
from src.document.presentation.routes import router as document_router
from src.images.presentation.routes import router as image_router
from src.locations.presentation.routes import router as locations_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(agents_router)
api_router.include_router(agents_turn_trace_router)
api_router.include_router(agents_test_drive_router)
api_router.include_router(nearby_location_router)
api_router.include_router(legacy_nearby_location_router)
api_router.include_router(agents_bottleneck_signal_router)
api_router.include_router(agents_conversation_router)
api_router.include_router(agents_review_router)
api_router.include_router(agents_reviews_router)
api_router.include_router(agents_sales_opportunity_router)
api_router.include_router(agents_customer_360_advisor_router)
api_router.include_router(agents_customer_360_admin_router)
api_router.include_router(agents_customer_360_meta_router)
api_router.include_router(agents_customer_router)
api_router.include_router(agents_memory_router)
api_router.include_router(agents_booking_router)
api_router.include_router(agents_history_router)
api_router.include_router(agents_notice_router)
api_router.include_router(agents_analytics_router)
api_router.include_router(agents_advisor_router)
api_router.include_router(admin_assignment_router)
api_router.include_router(auth_router)
api_router.include_router(staff_router)
api_router.include_router(admin_router)
api_router.include_router(document_router)
api_router.include_router(policy_notification_router)
api_router.include_router(document_admin_router)
api_router.include_router(image_router)
api_router.include_router(locations_router)
