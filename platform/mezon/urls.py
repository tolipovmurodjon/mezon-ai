from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

admin.site.site_header = "Mezon · boshqaruv"
admin.site.site_title = "Mezon"
admin.site.index_title = "Ma’lumotlar"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("kirish/", auth_views.LoginView.as_view(template_name="registration/login.html", redirect_authenticated_user=True), name="login"),
    path("chiqish/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("regulations.urls")),
]
