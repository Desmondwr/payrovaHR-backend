from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone
from datetime import timedelta
import secrets


class CustomUserManager(BaseUserManager):
    """Custom user manager where email is the unique identifier"""
    
    def create_user(self, email, password=None, **extra_fields):
        """Create and save a regular user with the given email and password"""
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """Create and save a superuser with the given email and password"""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('is_admin', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    """Custom user model with email as username field"""
    
    username = None  # Remove username field
    email = models.EmailField(unique=True, db_index=True)
    is_admin = models.BooleanField(default=False, help_text='Designates whether the user is a super admin')
    is_employer = models.BooleanField(default=False, help_text='Designates whether the user is an employer')
    is_employee = models.BooleanField(default=False, help_text='Designates whether the user is an employee')
    profile_completed = models.BooleanField(default=False, help_text='Designates whether the user has completed their profile')
    two_factor_enabled = models.BooleanField(default=False, help_text='Designates whether 2FA is enabled')
    two_factor_secret = models.CharField(max_length=32, blank=True, null=True, help_text='TOTP secret for 2FA')
    last_active_employer_id = models.IntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text='EmployerProfile ID most recently used by the user'
    )
    signature = models.ImageField(upload_to='user_signatures/', blank=True, null=True, help_text='Stored user signature image')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    class Meta:
        db_table = 'users'
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    def __str__(self):
        return self.email
    
    @property
    def employee_profile(self):
        """Get employee profile if user is an employee"""
        if not self.is_employee:
            return None
        
        # Try to get from cache
        if hasattr(self, '_employee_profile_cache'):
            return self._employee_profile_cache
        
        # Search for employee record in tenant databases
        from employees.models import Employee
        from accounts.database_utils import (
            get_tenant_database_alias,
            ensure_tenant_database_loaded,
        )
        
        try:
            # Prefer the last active employer when available
            if self.last_active_employer_id:
                membership = EmployeeMembership.objects.filter(
                    user_id=self.id,
                    employer_profile_id=self.last_active_employer_id,
                    status=EmployeeMembership.STATUS_ACTIVE,
                ).select_related('employer_profile').first()
                if membership and membership.employer_profile:
                    employer = membership.employer_profile
                    tenant_db = get_tenant_database_alias(employer)
                    ensure_tenant_database_loaded(employer)
                    try:
                        employee = Employee.objects.using(tenant_db).get(
                            id=membership.tenant_employee_id
                        ) if membership.tenant_employee_id else Employee.objects.using(tenant_db).get(
                            user_id=self.id
                        )
                        self._employee_profile_cache = employee
                        return employee
                    except Employee.DoesNotExist:
                        pass

            # Get all active employers
            employers = EmployerProfile.objects.filter(user__is_active=True).select_related('user')
            
            for employer in employers:
                tenant_db = get_tenant_database_alias(employer)
                ensure_tenant_database_loaded(employer)
                try:
                    employee = Employee.objects.using(tenant_db).get(user_id=self.id)
                    # Cache it
                    self._employee_profile_cache = employee
                    return employee
                except Employee.DoesNotExist:
                    continue
            
            return None
        except Exception:
            return None


class ActivationToken(models.Model):
    """Model to store account activation tokens"""
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activation_tokens')
    token = models.CharField(max_length=100, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    class Meta:
        db_table = 'activation_tokens'
        verbose_name = 'Activation Token'
        verbose_name_plural = 'Activation Tokens'
        ordering = ['-created_at']

    def __str__(self):
        return f"Token for {self.user.email}"

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(32)
        if not self.expires_at:
            # Token expires in 48 hours
            self.expires_at = timezone.now() + timedelta(hours=48)
        super().save(*args, **kwargs)

    def is_valid(self):
        """Check if token is valid (not expired and not used)"""
        return not self.is_used and timezone.now() < self.expires_at


class EmployerProfile(models.Model):
    """Model to store employer/company profile information"""
    
    ORGANIZATION_TYPES = [
        ('PRIVATE', 'Private Company'),
        ('NGO', 'Non-Governmental Organization'),
        ('GOVERNMENT', 'Government Agency'),
        ('PUBLIC', 'Public Company'),
        ('PARTNERSHIP', 'Partnership'),
        ('SOLE_PROPRIETOR', 'Sole Proprietorship'),
        ('OTHER', 'Other'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='employer_profile')
    
    # Company Information
    company_name = models.CharField(max_length=255)
    employer_name_or_group = models.CharField(max_length=255)
    organization_type = models.CharField(max_length=50, choices=ORGANIZATION_TYPES)
    industry_sector = models.CharField(max_length=255)
    date_of_incorporation = models.DateField()
    
    # Contact Information
    company_location = models.CharField(max_length=255, help_text='City/Region')
    physical_address = models.TextField()
    phone_number = models.CharField(max_length=20)
    fax_number = models.CharField(max_length=20, blank=True, null=True)
    official_company_email = models.EmailField()
    
    # Legal & Registration Documents
    rccm = models.CharField(max_length=100, help_text='Trade & Personal Property Credit Register')
    taxpayer_identification_number = models.CharField(max_length=50, help_text='NIU')
    cnps_employer_number = models.CharField(max_length=50, help_text='CNPS Employer Number')
    labour_inspectorate_declaration = models.CharField(max_length=100)
    business_license = models.CharField(max_length=100, help_text='Patente')
    
    # Financial Information
    bank_name = models.CharField(max_length=255)
    bank_account_number = models.CharField(max_length=50)
    bank_iban_swift = models.CharField(max_length=50, blank=True, null=True, help_text='IBAN/SWIFT code if applicable')
    
    # Database Information (for multi-tenancy)
    database_name = models.CharField(max_length=100, unique=True, null=True, blank=True, help_text='Tenant database name')
    database_created = models.BooleanField(default=False, help_text='Whether tenant database has been created')
    database_created_at = models.DateTimeField(null=True, blank=True, help_text='When the tenant database was created')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'employer_profiles'
        verbose_name = 'Employer Profile'
        verbose_name_plural = 'Employer Profiles'

    def __str__(self):
        return f"{self.company_name} - {self.user.email}"
    
    def get_database_alias(self):
        """Get the database alias for this employer's tenant database"""
        return f"tenant_{self.id}" if self.database_name else 'default'


class EmployeeMembership(models.Model):
    """Global mapping between a user and an employer tenant"""

    STATUS_INVITED = 'INVITED'
    STATUS_ACTIVE = 'ACTIVE'
    STATUS_TERMINATED = 'TERMINATED'

    STATUS_CHOICES = [
        (STATUS_INVITED, 'Invited'),
        (STATUS_ACTIVE, 'Active'),
        (STATUS_TERMINATED, 'Terminated'),
    ]

    ROLE_EMPLOYEE = 'EMPLOYEE'
    ROLE_MANAGER = 'MANAGER'
    ROLE_HR = 'HR'
    ROLE_ADMIN = 'ADMIN'

    ROLE_CHOICES = [
        (ROLE_EMPLOYEE, 'Employee'),
        (ROLE_MANAGER, 'Manager'),
        (ROLE_HR, 'HR'),
        (ROLE_ADMIN, 'Admin'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='memberships'
    )
    employer_profile = models.ForeignKey(
        EmployerProfile,
        on_delete=models.CASCADE,
        related_name='employee_memberships'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_INVITED)
    role = models.CharField(max_length=30, choices=ROLE_CHOICES, blank=True, null=True, help_text='Optional role label')
    permissions = models.JSONField(blank=True, null=True, help_text='Optional per-employer permissions')
    tenant_employee_id = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        help_text='Employee PK inside the employer tenant database (supports UUIDs)',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'employee_memberships'
        verbose_name = 'Employee Membership'
        verbose_name_plural = 'Employee Memberships'
        unique_together = ('user', 'employer_profile')
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['employer_profile', 'status']),
        ]

    def __str__(self):
        return f"{self.user.email} -> {self.employer_profile.company_name} ({self.status})"


class EmployeeRegistry(models.Model):
    """Central registry for cross-institutional employee tracking"""
    
    GENDER_CHOICES = [
        ('MALE', 'Male'),
        ('FEMALE', 'Female'),
        ('OTHER', 'Other'),
        ('PREFER_NOT_TO_SAY', 'Prefer not to say'),
    ]
    
    MARITAL_STATUS_CHOICES = [
        ('SINGLE', 'Single'),
        ('MARRIED', 'Married'),
        ('DIVORCED', 'Divorced'),
        ('WIDOWED', 'Widowed'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='employee_registry')
    
    # Personal Information
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True, null=True)
    date_of_birth = models.DateField()
    gender = models.CharField(max_length=20, choices=GENDER_CHOICES)
    marital_status = models.CharField(max_length=20, choices=MARITAL_STATUS_CHOICES)
    nationality = models.CharField(max_length=100)
    
    # Contact Information
    phone_number = models.CharField(max_length=20)
    alternative_phone = models.CharField(max_length=20, blank=True, null=True)
    personal_email = models.EmailField(blank=True, null=True)
    address = models.TextField()
    city = models.CharField(max_length=100)
    state_region = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20, blank=True, null=True)
    country = models.CharField(max_length=100)
    
    # Emergency Contact
    emergency_contact_name = models.CharField(max_length=200)
    emergency_contact_relationship = models.CharField(max_length=100)
    emergency_contact_phone = models.CharField(max_length=20)
    
    # Identification
    national_id_number = models.CharField(max_length=50, unique=True)
    passport_number = models.CharField(max_length=50, blank=True, null=True, unique=True)
    
    # Employment Preferences (for initial registration)
    desired_position = models.CharField(max_length=255, blank=True, null=True)
    years_of_experience = models.IntegerField(default=0)
    highest_education_level = models.CharField(max_length=100, blank=True, null=True)
    skills = models.TextField(blank=True, null=True, help_text='Comma-separated list of skills')
    
    # Profile Picture
    profile_picture = models.ImageField(upload_to='employee_profiles/', blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'employee_registry'
        verbose_name = 'Employee Registry'
        verbose_name_plural = 'Employee Registry'

    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.user.email}"


