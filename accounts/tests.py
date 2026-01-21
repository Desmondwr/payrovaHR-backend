from datetime import date

from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import EmployerProfile, EmployeeMembership, User
from employees.models import Employee


def create_employer_profile(user, name_suffix="ACME"):
    """Helper to build a minimally valid employer profile"""
    return EmployerProfile.objects.create(
        user=user,
        company_name=f"{name_suffix} Corp",
        employer_name_or_group=f"{name_suffix} Group",
        organization_type='PRIVATE',
        industry_sector='Technology',
        date_of_incorporation=date(2020, 1, 1),
        company_location='City',
        physical_address='123 Test Street',
        phone_number='123456789',
        official_company_email=f"{name_suffix.lower()}@example.com",
        rccm='RCCM123',
        taxpayer_identification_number='TIN123',
        cnps_employer_number='CNPS123',
        labour_inspectorate_declaration='DECL123',
        business_license='LICENSE123',
        bank_name='Test Bank',
        bank_account_number='1234567890',
    )


class EmployeeMembershipModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='employee@example.com', password='pass', is_employee=True)
        employer_user = User.objects.create_user(email='employer@example.com', password='pass', is_employer=True)
        self.employer_profile = create_employer_profile(employer_user)

    def test_membership_creation_and_uniqueness(self):
        membership = EmployeeMembership.objects.create(
            user=self.user,
            employer_profile=self.employer_profile,
            status=EmployeeMembership.STATUS_ACTIVE,
            tenant_employee_id=11,
        )
        self.assertEqual(membership.status, EmployeeMembership.STATUS_ACTIVE)
        with self.assertRaises(IntegrityError):
            EmployeeMembership.objects.create(
                user=self.user,
                employer_profile=self.employer_profile,
                status=EmployeeMembership.STATUS_INVITED,
            )


class MembershipEndpointsTests(APITestCase):
    def setUp(self):
        self.employee_user = User.objects.create_user(email='emp@example.com', password='pass', is_employee=True)
        employer_user = User.objects.create_user(email='boss@example.com', password='pass', is_employer=True)
        self.employer_profile = create_employer_profile(employer_user, name_suffix="BOSS")

    def test_list_active_employers(self):
        EmployeeMembership.objects.create(
            user=self.employee_user,
            employer_profile=self.employer_profile,
            status=EmployeeMembership.STATUS_ACTIVE,
            role=EmployeeMembership.ROLE_EMPLOYEE,
        )
        self.client.force_authenticate(user=self.employee_user)
        url = reverse('accounts:my-employers')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data.get('data', [])), 1)
        self.assertEqual(response.data['data'][0]['employer_id'], self.employer_profile.id)
        self.assertEqual(response.data['data'][0]['status'], EmployeeMembership.STATUS_ACTIVE)

    def test_set_active_employer_rejects_inactive_membership(self):
        EmployeeMembership.objects.create(
            user=self.employee_user,
            employer_profile=self.employer_profile,
            status=EmployeeMembership.STATUS_INVITED,
        )
        self.client.force_authenticate(user=self.employee_user)
        url = reverse('accounts:set-active-employer')
        response = self.client.post(url, {'employer_id': self.employer_profile.id}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIsNone(User.objects.get(id=self.employee_user.id).last_active_employer_id)


class EmployeeMembershipSignalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='signal@example.com', password='pass', is_employee=True)
        employer_user = User.objects.create_user(email='signal-employer@example.com', password='pass', is_employer=True)
        self.employer_profile = create_employer_profile(employer_user, name_suffix="SIG")

    def test_membership_created_on_employee_save(self):
        emp = Employee.objects.create(
            employer_id=self.employer_profile.id,
            user_id=self.user.id,
            first_name='Sig',
            last_name='Test',
            job_title='Dev',
            employment_type='FULL_TIME',
            employment_status='ACTIVE',
            hire_date=date.today(),
            email='sig@test.com',
        )
        membership = EmployeeMembership.objects.filter(user=self.user, employer_profile=self.employer_profile).first()
        self.assertIsNotNone(membership)
        self.assertEqual(membership.tenant_employee_id, emp.id)
        self.assertEqual(membership.status, EmployeeMembership.STATUS_ACTIVE)

