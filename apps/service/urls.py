from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ServiceTypeViewSet, ServiceSiteViewSet, ServiceItemViewSet

router = DefaultRouter()
router.register(r'service-types', ServiceTypeViewSet, basename='service-type')
router.register(r'sites', ServiceSiteViewSet, basename='service-site')
router.register(r'items', ServiceItemViewSet, basename='service-item')

urlpatterns = [
    path('', include(router.urls)),
]
