from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ServiceTypeViewSet, ServiceSiteViewSet, ServiceItemViewSet, WorkbenchViewSet

router = DefaultRouter()
router.register(r'service-types', ServiceTypeViewSet, basename='service-type')
router.register(r'sites', ServiceSiteViewSet, basename='service-site')
router.register(r'items', ServiceItemViewSet, basename='service-item')
router.register(r'workbench', WorkbenchViewSet, basename='workbench')

urlpatterns = [
    path('', include(router.urls)),
]
