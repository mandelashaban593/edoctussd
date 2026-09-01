from django.urls import path
from .views import CalloutView, SuccessIPNView, FailureIPNView

app_name = "ussd"

urlpatterns = [
    path("callout/", CalloutView.as_view(), name="callout"),
    path("ipn/success/", SuccessIPNView.as_view(), name="ipn-success"),
    path("ipn/failure/", FailureIPNView.as_view(), name="ipn-failure"),
]