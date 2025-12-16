# Migration Guide - Employee Profile Completion Feature

## Quick Start

This guide helps you deploy the employee profile completion feature to your environment.

---

## Step 1: Verify Code Changes

All code changes are complete. Files modified:
- ✅ [employees/models.py](employees/models.py) - Made fields optional, added profile tracking
- ✅ [employees/serializers.py](employees/serializers.py) - New serializers, default invitation enabled
- ✅ [employees/views.py](employees/views.py) - New EmployeeProfileViewSet
- ✅ [employees/urls.py](employees/urls.py) - Added profile routes
- ✅ [accounts/models.py](accounts/models.py) - Added employee_profile property
- ✅ [accounts/views.py](accounts/views.py) - Login response includes profile status

---

## Step 2: Run Migrations

### Option A: Migrate All Databases (Recommended)

```bash
# Main database
python manage.py migrate

# All tenant databases
python manage.py migrate_tenant_databases
```

### Option B: Migrate Specific Tenant

```bash
# Find tenant database alias
python manage.py check_tenant_db <employer_id>

# Run migration
python manage.py migrate --database=tenant_<employer_id>
```

### Verify Migration

```bash
# Check migration status
python manage.py showmigrations employees

# Should show:
# [X] 0001_initial
# [X] 0002_alter_employee_employee_id
# [X] 0003_employee_profile_completed_and_more
```

---

## Step 3: Test the Implementation

### Test 1: Create Employee with Minimal Fields

```bash
# Get employer token first
TOKEN="your_employer_jwt_token"

# Create employee
curl -X POST http://localhost:8000/api/employees/employees/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "first_name": "Test",
    "last_name": "Employee",
    "email": "test.employee@example.com",
    "job_title": "Tester",
    "employment_type": "FULL_TIME",
    "hire_date": "2025-01-20"
  }'

# Should return employee data with invitation sent
```

### Test 2: Accept Invitation

```bash
# Use token from invitation email
curl -X POST http://localhost:8000/api/employees/invitations/accept/ \
  -H "Content-Type: application/json" \
  -d '{
    "token": "<invitation_token>",
    "password": "TestPassword123!",
    "confirm_password": "TestPassword123!"
  }'

# Should create user account and link to employee
```

### Test 3: Login as Employee

```bash
curl -X POST http://localhost:8000/api/accounts/login/ \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test.employee@example.com",
    "password": "TestPassword123!"
  }'

# Response should include:
# "employee_profile_completed": false
```

### Test 4: View Employee Profile

```bash
# Get employee token from login
EMPLOYEE_TOKEN="employee_jwt_token"

curl -X GET http://localhost:8000/api/employees/profile/me/ \
  -H "Authorization: Bearer $EMPLOYEE_TOKEN"

# Should return employee profile with many null fields
# "profile_completed": false
```

### Test 5: Complete Profile

```bash
curl -X PATCH http://localhost:8000/api/employees/profile/complete-profile/ \
  -H "Authorization: Bearer $EMPLOYEE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "date_of_birth": "1990-01-01",
    "gender": "MALE",
    "phone_number": "+237123456789",
    "address": "123 Test Street",
    "city": "Douala",
    "country": "Cameroon",
    "national_id_number": "123456789",
    "emergency_contact_name": "Emergency Contact",
    "emergency_contact_relationship": "Spouse",
    "emergency_contact_phone": "+237987654321"
  }'

# Should update profile and set profile_completed = true
```

### Test 6: Login Again

```bash
curl -X POST http://localhost:8000/api/accounts/login/ \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test.employee@example.com",
    "password": "TestPassword123!"
  }'

# Response should now include:
# "employee_profile_completed": true
```

---

## Step 4: Frontend Integration Points

### Login Handler Update

```javascript
// frontend/src/auth/login.js
async function handleLogin(email, password) {
  const response = await axios.post('/api/accounts/login/', {
    email,
    password
  });

  const { user, tokens, employee_profile_completed } = response.data;

  // Store token
  localStorage.setItem('access_token', tokens.access);
  localStorage.setItem('refresh_token', tokens.refresh);

  // Route based on user type and profile status
  if (user.is_employee) {
    if (employee_profile_completed === false) {
      router.push('/employee/complete-profile');
    } else {
      router.push('/employee/dashboard');
    }
  } else if (user.is_employer) {
    router.push('/employer/dashboard');
  }
}
```

### Employee Creation Form Update

```javascript
// frontend/src/employer/CreateEmployee.vue
<template>
  <form @submit.prevent="createEmployee">
    <!-- Required Fields Only -->
    <input v-model="employee.first_name" required placeholder="First Name" />
    <input v-model="employee.last_name" required placeholder="Last Name" />
    <input v-model="employee.email" type="email" required placeholder="Email" />
    <input v-model="employee.job_title" required placeholder="Job Title" />
    <select v-model="employee.employment_type" required>
      <option value="FULL_TIME">Full Time</option>
      <option value="PART_TIME">Part Time</option>
      <option value="CONTRACT">Contract</option>
    </select>
    <input v-model="employee.hire_date" type="date" required />
    
    <!-- Send Invitation Checkbox (Checked by Default) -->
    <label>
      <input v-model="employee.send_invitation" type="checkbox" checked />
      Send invitation email
    </label>
    
    <button type="submit">Create Employee</button>
  </form>
</template>

<script>
export default {
  data() {
    return {
      employee: {
        first_name: '',
        last_name: '',
        email: '',
        job_title: '',
        employment_type: 'FULL_TIME',
        hire_date: '',
        send_invitation: true  // Default true
      }
    }
  },
  methods: {
    async createEmployee() {
      const token = localStorage.getItem('access_token');
      const response = await axios.post(
        '/api/employees/employees/',
        this.employee,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      
      // Show success message
      alert('Employee created! Invitation sent to ' + this.employee.email);
      this.$router.push('/employer/employees');
    }
  }
}
</script>
```

### Profile Completion Form

```javascript
// frontend/src/employee/CompleteProfile.vue
<template>
  <div class="profile-completion">
    <h2>Complete Your Profile</h2>
    <p>Please fill in the required information to complete your profile.</p>
    
    <form @submit.prevent="completeProfile">
      <!-- Personal Information -->
      <h3>Personal Information</h3>
      <input v-model="profile.date_of_birth" type="date" required />
      <select v-model="profile.gender" required>
        <option value="MALE">Male</option>
        <option value="FEMALE">Female</option>
        <option value="OTHER">Other</option>
      </select>
      <input v-model="profile.nationality" required />
      
      <!-- Contact Information -->
      <h3>Contact Information</h3>
      <input v-model="profile.phone_number" type="tel" required />
      <textarea v-model="profile.address" required></textarea>
      <input v-model="profile.city" required />
      <input v-model="profile.country" required />
      
      <!-- Legal Identification -->
      <h3>Identification</h3>
      <input v-model="profile.national_id_number" required />
      
      <!-- Emergency Contact -->
      <h3>Emergency Contact</h3>
      <input v-model="profile.emergency_contact_name" required />
      <input v-model="profile.emergency_contact_relationship" required />
      <input v-model="profile.emergency_contact_phone" type="tel" required />
      
      <button type="submit">Complete Profile</button>
    </form>
  </div>
</template>

<script>
export default {
  data() {
    return {
      profile: {
        date_of_birth: '',
        gender: '',
        nationality: '',
        phone_number: '',
        address: '',
        city: '',
        country: '',
        national_id_number: '',
        emergency_contact_name: '',
        emergency_contact_relationship: '',
        emergency_contact_phone: ''
      }
    }
  },
  methods: {
    async completeProfile() {
      const token = localStorage.getItem('access_token');
      
      try {
        const response = await axios.patch(
          '/api/employees/profile/complete-profile/',
          this.profile,
          { headers: { Authorization: `Bearer ${token}` } }
        );
        
        // Success - redirect to dashboard
        alert('Profile completed successfully!');
        this.$router.push('/employee/dashboard');
      } catch (error) {
        // Handle validation errors
        console.error('Failed to complete profile:', error.response.data);
      }
    }
  }
}
</script>
```

---

## Step 5: Update Email Templates (Optional)

Update invitation email template to mention profile completion:

```html
<!-- templates/emails/employee_invitation.html -->
<p>Welcome to {{ company_name }}!</p>

<p>You have been added as an employee. Please accept this invitation to:</p>
<ul>
  <li>Create your account</li>
  <li>Complete your employee profile</li>
  <li>Access the employee portal</li>
</ul>

<p>
  <a href="{{ invitation_link }}">Accept Invitation</a>
</p>

<p>This invitation will expire in 7 days.</p>
```

---

## Step 6: Verify Permissions

Ensure permissions are configured correctly:

```python
# accounts/permissions.py should have:

class IsEmployee(permissions.BasePermission):
    """Permission for employees only"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_employee

class IsEmployer(permissions.BasePermission):
    """Permission for employers only"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_employer
```

---

## Step 7: Monitor and Debug

### Check Logs
```bash
# Watch Django logs
tail -f logs/django.log

# Check for errors during profile completion
grep "profile" logs/django.log
```

### Common Issues

**Issue**: Employee can't access `/profile/me/`
- **Solution**: Verify `is_employee=True` on user account
- **Check**: User has accepted invitation

**Issue**: `profile_completed` not updating
- **Solution**: Check migration ran on tenant database
- **Check**: Employee using PATCH/PUT to complete-profile endpoint

**Issue**: Login not returning `employee_profile_completed`
- **Solution**: Check `employee_profile` property on User model
- **Check**: Tenant database routing is working

---

## Rollback Plan (If Needed)

### Revert Migration

```bash
# Revert to previous migration
python manage.py migrate employees 0002_alter_employee_employee_id

# For tenant databases
python manage.py migrate employees 0002_alter_employee_employee_id --database=tenant_<employer_id>
```

### Revert Code Changes

```bash
git checkout HEAD~1 employees/models.py
git checkout HEAD~1 employees/serializers.py
git checkout HEAD~1 employees/views.py
git checkout HEAD~1 employees/urls.py
git checkout HEAD~1 accounts/models.py
git checkout HEAD~1 accounts/views.py
```

---

## Success Criteria

✅ Migration runs successfully on all databases  
✅ Employer can create employee with minimal fields  
✅ Invitation email sent automatically  
✅ Employee can accept invitation  
✅ Employee can login  
✅ Login response shows `employee_profile_completed: false`  
✅ Employee can access `/profile/me/`  
✅ Employee can complete profile  
✅ `profile_completed` updates to `true`  
✅ Future logins show `employee_profile_completed: true`  

---

## Support

For issues or questions, refer to:
- [EMPLOYEE_PROFILE_COMPLETION_IMPLEMENTATION.md](EMPLOYEE_PROFILE_COMPLETION_IMPLEMENTATION.md)
- [FRONTEND_EMPLOYEE_CREATION_GUIDE.md](FRONTEND_EMPLOYEE_CREATION_GUIDE.md)
- [EMPLOYEE_PROFILE_COMPLETION_REQUIREMENTS.md](EMPLOYEE_PROFILE_COMPLETION_REQUIREMENTS.md)

---

**Migration File**: `employees/migrations/0003_employee_profile_completed_and_more.py`  
**Status**: ✅ Ready for deployment  
**Estimated Time**: 10-15 minutes
