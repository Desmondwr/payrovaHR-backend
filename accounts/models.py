from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from datetime import timedelta
import secrets
import uuid


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
    is_employer_owner = models.BooleanField(default=False, help_text='Designates whether the user is the employer owner')
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

    COMPANY_SIZES = [
        ('1-10', '1-10'),
        ('11-50', '11-50'),
        ('51-200', '51-200'),
        ('201-500', '201-500'),
        ('501-1000', '501-1000'),
        ('1000+', '1000+'),
    ]
    
    # Company Information
    company_name = models.CharField(max_length=255)
    company_logo = models.ImageField(upload_to='company_logos/', blank=True, null=True)
    employer_name_or_group = models.CharField(max_length=255)
    organization_type = models.CharField(max_length=50, choices=ORGANIZATION_TYPES)
    industry_sector = models.CharField(max_length=255)
    date_of_incorporation = models.DateField()
    company_size = models.CharField(max_length=50, choices=COMPANY_SIZES, blank=True, null=True)
    company_tagline = models.CharField(max_length=255, blank=True, null=True)
    company_overview = models.TextField(blank=True, null=True)
    company_mission = models.TextField(blank=True, null=True)
    company_values = models.TextField(blank=True, null=True)
    company_benefits = models.TextField(blank=True, null=True)
    company_website = models.URLField(blank=True, null=True)
    careers_email = models.EmailField(blank=True, null=True)
    linkedin_url = models.URLField(blank=True, null=True)
    
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
    bank_name = models.CharField(max_length=255, blank=True, null=True)
    bank_account_number = models.CharField(max_length=50, blank=True, null=True)
    bank_iban_swift = models.CharField(max_length=50, blank=True, null=True, help_text='IBAN/SWIFT code if applicable')
    
    # Database Information (for multi-tenancy)
    database_name = models.CharField(max_length=100, unique=True, null=True, blank=True, help_text='Tenant database name')
    database_created = models.BooleanField(default=False, help_text='Whether tenant database has been created')
    database_created_at = models.DateTimeField(null=True, blank=True, help_text='When the tenant database was created')

    # Public Access
    slug = models.SlugField(max_length=100, unique=True, null=True, blank=True, help_text='URL-friendly identifier for public pages')

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

    def save(self, *args, **kwargs):
        if not self.slug and self.company_name:
            base = slugify(self.company_name)[:90] or "employer"
            slug = base
            counter = 1
            while EmployerProfile.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)


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


class Permission(models.Model):
    """RBAC permission definition (global catalog)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=200, unique=True)
    module = models.CharField(max_length=50, db_index=True)
    resource = models.CharField(max_length=50)
    action = models.CharField(max_length=50)
    scope = models.CharField(max_length=50)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "rbac_permissions"
        verbose_name = "Permission"
        verbose_name_plural = "Permissions"
        ordering = ["module", "resource", "action", "scope"]

    def __str__(self):
        return self.code


class Role(models.Model):
    """Employer-scoped RBAC role."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer = models.ForeignKey(
        EmployerProfile, on_delete=models.CASCADE, related_name="roles"
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    is_system_role = models.BooleanField(
        default=False, help_text="Template/system role indicator"
    )
    is_active = models.BooleanField(default=True)
    allow_high_risk_combination = models.BooleanField(
        default=False,
        help_text="Allow payroll input + treasury release combinations (owner only).",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="roles_created",
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "rbac_roles"
        verbose_name = "Role"
        verbose_name_plural = "Roles"
        unique_together = ("employer", "name")
        indexes = [
            models.Index(fields=["employer", "is_active"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.employer_id})"


class RolePermission(models.Model):
    """Join table between Role and Permission."""

    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="role_permissions")
    permission = models.ForeignKey(
        Permission, on_delete=models.CASCADE, related_name="role_permissions"
    )

    class Meta:
        db_table = "rbac_role_permissions"
        verbose_name = "Role Permission"
        verbose_name_plural = "Role Permissions"
        unique_together = ("role", "permission")
        indexes = [
            models.Index(fields=["role", "permission"]),
        ]

    def __str__(self):
        return f"{self.role_id}:{self.permission_id}"


class EmployeeRole(models.Model):
    """Role assignment for an employee/user within an employer."""

    SCOPE_COMPANY = "COMPANY"
    SCOPE_BRANCH = "BRANCH"
    SCOPE_DEPARTMENT = "DEPARTMENT"
    SCOPE_SELF = "SELF"

    SCOPE_CHOICES = [
        (SCOPE_COMPANY, "Company"),
        (SCOPE_BRANCH, "Branch"),
        (SCOPE_DEPARTMENT, "Department"),
        (SCOPE_SELF, "Self"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer = models.ForeignKey(
        EmployerProfile, on_delete=models.CASCADE, related_name="employee_roles"
    )
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="employee_roles")
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="employee_roles",
        blank=True,
        null=True,
    )
    employee_id = models.CharField(
        max_length=64,
        db_index=True,
        help_text="Employee PK inside the employer tenant database (supports UUIDs)",
    )
    scope_type = models.CharField(
        max_length=20, choices=SCOPE_CHOICES, default=SCOPE_COMPANY
    )
    scope_id = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        help_text="Optional branch/department scope identifier (UUID as string).",
    )
    assigned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="roles_assigned",
        blank=True,
        null=True,
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "rbac_employee_roles"
        verbose_name = "Employee Role"
        verbose_name_plural = "Employee Roles"
        unique_together = ("employer", "employee_id", "role", "scope_type", "scope_id")
        indexes = [
            models.Index(fields=["employer", "employee_id"]),
            models.Index(fields=["user", "employer"]),
        ]

    def __str__(self):
        return f"{self.employee_id} -> {self.role.name}"


class UserPermissionOverride(models.Model):
    """Per-user permission overrides (allow/deny)."""

    EFFECT_ALLOW = "ALLOW"
    EFFECT_DENY = "DENY"
    EFFECT_CHOICES = [
        (EFFECT_ALLOW, "Allow"),
        (EFFECT_DENY, "Deny"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employer = models.ForeignKey(
        EmployerProfile, on_delete=models.CASCADE, related_name="permission_overrides"
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="permission_overrides"
    )
    permission = models.ForeignKey(
        Permission, on_delete=models.CASCADE, related_name="user_overrides"
    )
    effect = models.CharField(max_length=10, choices=EFFECT_CHOICES)
    reason = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="permission_overrides_created",
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "rbac_user_permission_overrides"
        verbose_name = "User Permission Override"
        verbose_name_plural = "User Permission Overrides"
        unique_together = ("employer", "user", "permission")
        indexes = [
            models.Index(fields=["employer", "user"]),
        ]

    def __str__(self):
        return f"{self.user_id}:{self.permission.code}:{self.effect}"


class AuditLog(models.Model):
    """RBAC audit log entries."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    action = models.CharField(max_length=100)
    entity_type = models.CharField(max_length=50)
    entity_id = models.CharField(max_length=64)
    meta_old = models.TextField(blank=True, null=True)
    meta_new = models.TextField(blank=True, null=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True, null=True)
    actor = models.ForeignKey(
        User, on_delete=models.SET_NULL, related_name="audit_actions", blank=True, null=True
    )
    employer = models.ForeignKey(
        EmployerProfile,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "rbac_audit_logs"
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["employer", "created_at"]),
            models.Index(fields=["action"]),
        ]

    def __str__(self):
        return f"{self.action} {self.entity_type}:{self.entity_id}"
