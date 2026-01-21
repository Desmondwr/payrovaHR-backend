from django.urls import path

from .views import NotificationListView, NotificationMarkReadView

app_name = 'notifications'

urlpatterns = [
    path('', NotificationListView.as_view(), name='notifications'),
    path('mark-read/', NotificationMarkReadView.as_view(), name='notifications-mark-read'),
]
