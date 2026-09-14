from django.urls import path

from .views import WarningsView

app_name = "warnings"

urlpatterns = [path("", WarningsView.as_view(), name="list")]
