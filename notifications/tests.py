from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from notifications.models import Notification


class NotificationTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='notify@example.com', password='pass')
        Notification.objects.create(user=self.user, title='Test', body='Hello')
        Notification.objects.create(user=self.user, title='Read', body='World', status=Notification.STATUS_READ)

    def test_list_notifications(self):
        self.client.force_authenticate(self.user)
        url = reverse('notifications:notifications')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data.get('data', [])), 2)

    def test_mark_read(self):
        note = Notification.objects.create(user=self.user, title='Unread', body='Body')
        self.client.force_authenticate(self.user)
        url = reverse('notifications:notifications-mark-read')
        resp = self.client.post(url, {'notification_ids': [note.id]}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        note.refresh_from_db()
        self.assertEqual(note.status, Notification.STATUS_READ)
