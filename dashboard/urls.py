from django.urls import re_path
from django.contrib.auth.views import LogoutView
from . import views
from dashboard.views import *

app_name = "dashboard"

urlpatterns = [
    re_path(r"^login/$", DashboardLoginView.as_view(), name="login"),
    re_path(r"^logout/$", LogoutView.as_view(), name="logout"),
    re_path(r"^$", DashboardHomeView.as_view(), name="home"),

    re_path(
        r"^transactions/$",
        TransactionListView.as_view(),
        name="transactions"
    ),

    re_path(
        r"^transactions/export/$",
        TransactionExportCSVView.as_view(),
        name="transactions-export"
    ),

    re_path(
        r"^providers/$",
        ProviderListView.as_view(),
        name="providers"
    ),

    re_path(
        r"^providers/new/$",
        ProviderCreateView.as_view(),
        name="provider-create"
    ),

    re_path(
        r"^providers/(?P<pk>\d+)/edit/$",
        ProviderUpdateView.as_view(),
        name="provider-edit"
    ),

    re_path(r"^callout/$", CalloutView.as_view(), name="callout"),
    re_path(r"^ipn/success/$", SuccessIPNView.as_view(), name="ipn-success"),
    re_path(r"^ipn/failure/$", FailureIPNView.as_view(), name="ipn-failure"),
]