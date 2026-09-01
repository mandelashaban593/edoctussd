from django.contrib.auth.views import LogoutView
from django.urls import path
from . import views

app_name = "dashboard"

urlpatterns = [
    path("login/", views.DashboardLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("", views.DashboardHomeView.as_view(), name="home"),
    path("transactions/", views.TransactionListView.as_view(), name="transactions"),
    path("transactions/export/", views.TransactionExportCSVView.as_view(), name="transactions-export"),
    path("providers/", views.ProviderListView.as_view(), name="providers"),
    path("providers/new/", views.ProviderCreateView.as_view(), name="provider-create"),
    path("providers/<int:pk>/edit/", views.ProviderUpdateView.as_view(), name="provider-edit"),
]