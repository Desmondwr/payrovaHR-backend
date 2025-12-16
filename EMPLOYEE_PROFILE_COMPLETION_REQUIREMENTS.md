# Employee Profile Completion Workflow - Implementation Requirements

## Date: December 16, 2025

## Overview

This document outlines the required code changes to implement the improved employee onboarding workflow where:
1. **Employer** creates employee with minimal information
2. **Invitation** sent automatically (default behavior)
3. **Employee** accepts invitation and logs in
4. **Employee** completes their own profile

---

## Current vs Desired Workflow

### Current Workflow ❌
1. Employer creates employee with ALL required fields
2. Employer optionally sends invitation
3. Employee accepts invitation (creates user account)
4. Employee logs in - profile already complete

### Desired Workflow ✅
1. Employer creates employee with MINIMAL fields (name, email, job title, hire date)
2. Invitation sent AUTOMATICALLY (default: send_invitation=true)
3. Employee accepts invitation (creates user account + sets password)
4. Employee logs in and is redirected to COMPLETE PROFILE page
5. Employee fills in remaining required fields
6. Profile marked as complete

---

## Required Code Changes

### 1. Make Most Fields Optional in Employee Model

**File**: `employees/models.py`

**Changes Needed**:
- Make most fields `blank=True, null=True` except core fields
- Add `profile_completed` field to track completion status
- Add `profile_completed_at` timestamp field

```python
class Employee(models.Model):
    # ... existing fields ...
    
    # Core fields (always required by employer)
    first_name = models.CharField(max_length=100)  # Required
    last_name = models.CharField(max_length=100)   # Required
    email = models.EmailField()                     # Required
    job_title = models.CharField(max_length=255)   # Required
    hire_date = models.DateField()                 # Required
    employment_type = models.CharField(...)        # Required
    
    # Fields that can be completed by employee later
    phone_number = models.CharField(max_length=20, blank=True, null=True)  # Make optional
    date_of_birth = models.DateField(blank=True, null=True)  # Make optional
    address = models.TextField(blank=True, null=True)  # Make optional
    national_id_number = models.CharField(max_length=50, blank=True, null=True, db_index=True)  # Make optional
    emergency_contact_name = models.CharField(max_length=200, blank=True, null=True)  # Make optional
    # ... etc for other fields that employee should complete
    
    # NEW FIELDS - Profile completion tracking
    profile_completed = models.BooleanField(default=False, 
        help_text='Whether employee has completed their profile')
    profile_completed_at = models.DateTimeField(null=True, blank=True,
        help_text='When employee completed their profile')
```

**Migration Required**: Yes - `python manage.py makemigrations employees`

---

### 2. Change Default for send_invitation

**File**: `employees/serializers.py`

**Changes Needed**:
- Make `send_invitation` default to `True` instead of `False`

```python
class CreateEmployeeSerializer(serializers.ModelSerializer):
    send_invitation = serializers.BooleanField(default=True, write_only=True)  # Changed from False
    # ... rest of serializer
```

```python
class CreateEmployeeWithDetectionSerializer(serializers.ModelSerializer):
    send_invitation = serializers.BooleanField(default=True, write_only=True)  # Changed from False
    # ... rest of serializer
```

**Migration Required**: No

---

### 3. Update Validation to Allow Minimal Fields

**File**: `employees/serializers.py`

**Changes Needed**:
- Update validation to only require minimal fields during creation
- Validation should check if fields are required based on `profile_completed` status

```python
class CreateEmployeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employee
        fields = [
            # Minimal required fields for employer
            'first_name', 'last_name', 'email', 'job_title', 
            'employment_type', 'hire_date',
            
            # Optional fields (employee will complete later)
            'phone_number', 'date_of_birth', 'address', 
            'national_id_number', 'emergency_contact_name',
            # ... all other fields as optional
            
            'send_invitation'
        ]
        extra_kwargs = {
            # Only these are required during initial creation
            'first_name': {'required': True},
            'last_name': {'required': True},
            'email': {'required': True},
            'job_title': {'required': True},
            'employment_type': {'required': True},
            'hire_date': {'required': True},
            
            # Everything else is optional initially
            'phone_number': {'required': False},
            'date_of_birth': {'required': False},
            'address': {'required': False},
            'national_id_number': {'required': False},
            'emergency_contact_name': {'required': False},
            # ... etc
        }
```

**Migration Required**: No

---

### 4. Add Employee Profile Completion Endpoint

**File**: `employees/views.py`

**Changes Needed**:
- Add new endpoint for employees to complete their profile
- Add endpoint to get current employee's profile
- Add permission class for employees

```python
class EmployeeProfileViewSet(viewsets.ViewSet):
    """ViewSet for employee self-service profile management"""
    
    permission_classes = [IsAuthenticated, IsEmployee]
    
    @action(detail=False, methods=['get'])
    def me(self, request):
        """Get current employee's profile"""
        try:
            # Get employee record from tenant database
            from accounts.models import EmployerProfile
            
            # Find employee record by user_id across all tenant databases
            # This requires searching tenant databases for employee with matching user_id
            # Implementation depends on how you want to handle this
            
            employee = self._find_employee_by_user_id(request.user.id)
            
            if not employee:
                return Response(
                    {'error': 'Employee record not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            serializer = EmployeeDetailSerializer(employee)
            return Response(serializer.data)
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['put', 'patch'])
    def complete_profile(self, request):
        """Allow employee to complete their profile"""
        try:
            employee = self._find_employee_by_user_id(request.user.id)
            
            if not employee:
                return Response(
                    {'error': 'Employee record not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Get tenant database
            employer_id = employee.employer_id
            tenant_db = f"tenant_{employer_id}"
            
            # Get configuration to check required fields
            try:
                config = EmployeeConfiguration.objects.using(tenant_db).get(
                    employer_id=employer_id
                )
            except EmployeeConfiguration.DoesNotExist:
                config = None
            
            # Validate that all required fields are provided
            errors = self._validate_profile_completion(request.data, config)
            if errors:
                return Response(errors, status=status.HTTP_400_BAD_REQUEST)
            
            # Update employee record
            for field, value in request.data.items():
                if hasattr(employee, field) and field not in ['id', 'employer_id', 'user_id']:
                    setattr(employee, field, value)
            
            # Mark profile as completed
            employee.profile_completed = True
            employee.profile_completed_at = timezone.now()
            employee.save(using=tenant_db)
            
            # Create audit log
            create_employee_audit_log(
                employee=employee,
                action='PROFILE_COMPLETED',
                performed_by=request.user,
                notes='Employee completed their profile',
                request=request,
                tenant_db=tenant_db
            )
            
            return Response({
                'message': 'Profile completed successfully',
                'profile_completed': True,
                'employee': EmployeeDetailSerializer(employee).data
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _find_employee_by_user_id(self, user_id):
        """Find employee record by user_id across tenant databases"""
        # This needs to search across all tenant databases
        # One approach: Cache the mapping of user_id -> (employer_id, employee_id)
        # Another approach: Query all tenant databases (less efficient)
        
        from django.conf import settings
        from accounts.models import EmployerProfile
        
        # Get all employers with created databases
        employers = EmployerProfile.objects.filter(database_created=True)
        
        for employer in employers:
            tenant_db = f"tenant_{employer.id}"
            try:
                employee = Employee.objects.using(tenant_db).filter(
                    user_id=user_id
                ).first()
                if employee:
                    return employee
            except Exception:
                continue
        
        return None
    
    def _validate_profile_completion(self, data, config):
        """Validate that all required fields are provided"""
        errors = {}
        
        if not config:
            # Use default required fields
            required_fields = [
                'phone_number', 'address', 'date_of_birth', 
                'national_id_number', 'emergency_contact_name',
                'emergency_contact_relationship', 'emergency_contact_phone'
            ]
        else:
            # Check configuration for required fields
            required_fields = []
            if config.require_phone_number == 'REQUIRED':
                required_fields.append('phone_number')
            if config.require_address == 'REQUIRED':
                required_fields.append('address')
            # ... check all configurable fields
        
        for field in required_fields:
            if field not in data or not data[field]:
                errors[field] = [f'{field.replace("_", " ").title()} is required']
        
        return errors if errors else None
```

**Add to urls.py**:
```python
router.register(r'profile', EmployeeProfileViewSet, basename='employee-profile')
```

**Migration Required**: No

---

### 5. Add Serializer for Employee Profile Update

**File**: `employees/serializers.py`

**Changes Needed**:
- Add serializer for employee self-update

```python
class EmployeeProfileCompletionSerializer(serializers.ModelSerializer):
    """Serializer for employee to complete their own profile"""
    
    class Meta:
        model = Employee
        fields = [
            # Fields employee can update
            'phone_number', 'personal_email', 'alternative_phone',
            'address', 'city', 'state_region', 'postal_code', 'country',
            'date_of_birth', 'gender', 'marital_status', 'nationality',
            'national_id_number', 'passport_number', 'cnps_number', 'tax_number',
            'bank_name', 'bank_account_number', 'bank_account_name',
            'emergency_contact_name', 'emergency_contact_relationship',
            'emergency_contact_phone', 'profile_photo'
        ]
        # Employee cannot change these fields
        read_only_fields = [
            'id', 'employer_id', 'employee_id', 'user_id',
            'first_name', 'last_name', 'email', 'job_title',
            'employment_type', 'employment_status', 'hire_date',
            'department', 'branch', 'manager'
        ]
```

**Migration Required**: No

---

### 6. Update Login Response to Include Profile Status

**File**: `accounts/views.py` (or wherever login is handled)

**Changes Needed**:
- Include `profile_completed` status in login response for employees

```python
class LoginView(APIView):
    def post(self, request):
        # ... existing login logic ...
        
        # For employees, check profile completion status
        if user.is_employee:
            # Find employee record
            employee = find_employee_by_user_id(user.id)
            if employee:
                response_data['profile_incomplete'] = not employee.profile_completed
                response_data['profile_completed'] = employee.profile_completed
        
        return Response(response_data)
```

**Migration Required**: No

---

### 7. Add User-Employee Mapping Cache (Optional but Recommended)

**File**: New file `employees/employee_cache.py`

**Purpose**: Cache the mapping of user_id to employee location to avoid searching all tenant databases

```python
"""Cache for employee-user mappings"""
from django.core.cache import cache

def cache_employee_mapping(user_id, employer_id, employee_id):
    """Cache the mapping of user_id to employee location"""
    cache_key = f"employee_mapping_{user_id}"
    cache.set(cache_key, {
        'employer_id': employer_id,
        'employee_id': str(employee_id)
    }, timeout=3600)  # Cache for 1 hour

def get_employee_mapping(user_id):
    """Get cached employee mapping"""
    cache_key = f"employee_mapping_{user_id}"
    return cache.get(cache_key)

def clear_employee_mapping(user_id):
    """Clear cached employee mapping"""
    cache_key = f"employee_mapping_{user_id}"
    cache.delete(cache_key)
```

**Update invitation acceptance to cache mapping**:
```python
# In views.py - accept invitation
def accept(self, request):
    # ... existing code ...
    
    # After linking user to employee
    from employees.employee_cache import cache_employee_mapping
    cache_employee_mapping(user.id, employee.employer_id, employee.id)
    
    # ... rest of code
```

**Migration Required**: No

---

## Testing Checklist

### Backend Testing

- [ ] Employee creation works with minimal fields only
- [ ] Invitation is sent by default (send_invitation=true)
- [ ] Employee can accept invitation
- [ ] Employee can login after acceptance
- [ ] `/api/employees/profile/me/` returns employee profile
- [ ] `/api/employees/profile/complete_profile/` accepts profile updates
- [ ] `profile_completed` flag is set after completion
- [ ] Validation enforces required fields based on configuration
- [ ] Employee cannot update restricted fields (job_title, salary, etc.)
- [ ] Audit log created on profile completion

### Frontend Testing

- [ ] Employer form only requires minimal fields
- [ ] Employee receives invitation email
- [ ] Employee can accept invitation
- [ ] After login, employee redirected to profile completion
- [ ] Profile completion form shows correct required fields
- [ ] Profile completion form validates correctly
- [ ] After completion, employee can access dashboard
- [ ] Profile completion status tracked correctly

---

## Migration Steps

### 1. Update Models
```bash
# Make fields optional and add profile_completed fields
python manage.py makemigrations employees
python manage.py migrate  # Migrate main database
python manage.py migrate employees --database=tenant_1  # Migrate each tenant database
```

### 2. Update Existing Employee Records
```python
# Set profile_completed=True for existing employees
# Run this management command after migration

from employees.models import Employee
from django.conf import settings

# For each tenant database
for employer in EmployerProfile.objects.filter(database_created=True):
    tenant_db = f"tenant_{employer.id}"
    Employee.objects.using(tenant_db).all().update(
        profile_completed=True,
        profile_completed_at=timezone.now()
    )
```

### 3. Deploy Code Changes
- Deploy updated models, serializers, views
- Test with new employee creation
- Monitor logs for errors

---

## Frontend Changes Required

### 1. Employer Employee Creation Form
- Simplify form to only show minimal required fields
- Add "Advanced" section for optional fields
- Show message: "Employee will complete remaining details after accepting invitation"

### 2. Employee Profile Completion Page
- Create new route: `/employee/complete-profile`
- Form to collect remaining required fields
- Show progress indicator
- Validate based on organization configuration

### 3. Employee Dashboard
- Check profile completion status on login
- Redirect to completion page if incomplete
- Show completion prompt/banner if incomplete

### 4. Navigation Guard
```javascript
// React Router example
const PrivateRoute = ({ children }) => {
  const user = useAuth();
  
  if (user.is_employee && user.profile_incomplete) {
    return <Navigate to="/employee/complete-profile" />;
  }
  
  return children;
};
```

---

## API Endpoints Summary

### New Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/employees/profile/me/` | Employee | Get current employee's profile |
| PUT/PATCH | `/api/employees/profile/complete_profile/` | Employee | Complete profile |

### Modified Behavior

| Endpoint | Change |
|----------|--------|
| `POST /api/employees/employees/` | Now requires only minimal fields, send_invitation defaults to true |

---

## Benefits of This Workflow

✅ **Better UX** - Employee completes their own sensitive information  
✅ **Data Privacy** - Employer doesn't handle employee's personal details  
✅ **Accuracy** - Employee provides their own accurate information  
✅ **GDPR Compliant** - Employee controls their own data  
✅ **Reduced Employer Burden** - Less data entry for employer  
✅ **Self-Service** - Employees empowered to manage their profile

---

## Estimated Implementation Time

- Model changes: 1 hour
- Serializer updates: 1 hour
- View/endpoint creation: 2-3 hours
- Testing: 2 hours
- Migration script: 1 hour
- Frontend updates: 4-6 hours

**Total**: ~12-15 hours of development time

---

**Document Created**: December 16, 2025  
**Status**: Requirements Defined - Awaiting Implementation
