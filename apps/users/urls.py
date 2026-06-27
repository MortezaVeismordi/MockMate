from django.urls import include, path

from . import views

app_name = "users"

auth_urlpatterns = [
    path("send-otp/", views.SendOTPView.as_view(), name="send-otp"),
    path("resend-otp/", views.ResendOTPView.as_view(), name="resend-otp"),
    path("verify-otp/", views.VerifyOTPView.as_view(), name="verify-otp"),
    path("refresh-token/", views.RefreshTokenView.as_view(), name="refresh-token"),
    path(
        "login-password/", views.LoginWithPasswordView.as_view(), name="login-password"
    ),
    path("logout/", views.LogoutView.as_view(), name="logout"),
]

profile_urlpatterns = [
    path("", views.UserMeView.as_view(), name="me"),
    path("delete/", views.DeleteAccountView.as_view(), name="delete-account"),
    path("avatar/", views.AvatarView.as_view(), name="avatar"),
    path(
        "complete-profile/",
        views.CompleteProfileView.as_view(),
        name="complete-profile",
    ),
    path("set-password/", views.SetPasswordView.as_view(), name="set-password"),
]

admin_urlpatterns = [
    path("users/", views.AdminUserListView.as_view(), name="admin-user-list"),
    path(
        "users/<int:pk>/", views.AdminUserDetailView.as_view(), name="admin-user-detail"
    ),
    path(
        "users/<int:pk>/suspend/",
        views.AdminSuspendUserView.as_view(),
        name="admin-suspend",
    ),
    path(
        "users/<int:pk>/unsuspend/",
        views.AdminUnsuspendUserView.as_view(),
        name="admin-unsuspend",
    ),
    path("users/<int:pk>/ban/", views.AdminBanUserView.as_view(), name="admin-ban"),
    path(
        "otp-history/<int:user_id>/",
        views.AdminOTPHistoryView.as_view(),
        name="admin-otp-history",
    ),
    path("stats/", views.AdminStatsView.as_view(), name="admin-stats"),
]

urlpatterns = [
    path("auth/", include(auth_urlpatterns)),
    path("me/", include(profile_urlpatterns)),
    path("admin/", include(admin_urlpatterns)),
]
