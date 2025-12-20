# HR System User Manual

## Table of Contents
1. [Introduction](#introduction)
2. [System Overview](#system-overview)
3. [Getting Started](#getting-started)
4. [User Roles](#user-roles)
5. [Employer Guide](#employer-guide)
6. [Employee Guide](#employee-guide)
7. [Key Features](#key-features)
8. [Frequently Asked Questions](#frequently-asked-questions)
9. [Troubleshooting](#troubleshooting)

---

## Introduction

Welcome to the HR Management System! This is a comprehensive Human Resources platform designed to help employers manage their workforce efficiently while providing employees with easy access to their employment information.

### What This System Does

- **For Employers**: Register your company, create employee accounts, manage workforce data, and track employment records
- **For Employees**: Access your employment information, complete your profile, and manage your personal data
- **Cross-Institutional Tracking**: Prevents duplicate employee registrations across different companies using a central registry

---

## System Overview

### Multi-Tenant Architecture

Each employer (company) gets their own isolated database space called a "tenant." This means:
- Your company data is completely separate from other companies
- Employees can only access data from their employer's database
- Each company operates independently with full data privacy

### Central Employee Registry

While each company has separate data, the system maintains a central registry that:
- Tracks all employees across all institutions
- Prevents employees from being registered at multiple companies simultaneously
- Uses national ID numbers as the unique identifier
- Ensures data integrity across the entire system

---

## Getting Started

### Prerequisites

- Internet connection
- Valid email address
- National ID number (for employees)
- Business registration number (for employers)

### System Access

The system is accessed through API endpoints at:
```
http://127.0.0.1:8000/api/
```

You'll need an API client like Postman or Insomnia to interact with the system.

---

## User Roles

### 1. Employer
**Who**: Company owners, HR managers, or authorized personnel  
**Can Do**:
- Register their company
- Create employee accounts
- Approve employee self-registrations
- Manage employee data
- Update company information

### 2. Employee
**Who**: Staff members working for a registered company  
**Can Do**:
- Login to access their profile
- View employment information
- Complete and update personal information
- Request changes to employment data

---

## Employer Guide

### Step 1: Company Registration

**What You Need**:
- Company email address
- Secure password
- Company name
- Business registration number
- Industry sector
- Company size
- Contact details
- Physical address

**What Happens**:
1. You submit your company information
2. System creates your company profile
3. System automatically creates a dedicated database for your company
4. You receive access tokens for immediate login
5. You can now start adding employees

**Result**: Your company is registered and you have a secure, isolated workspace for your HR data.

---

### Step 2: Managing Employees

You have **two methods** to add employees:

#### Method 1: You Create Employee Accounts (Recommended for Bulk Onboarding)

**When to Use**: 
- Hiring new employees
- Bulk employee onboarding
- When you have all employee information

**Process**:
1. Gather employee information (including national ID)
2. Create employee account through the system
3. System automatically checks for duplicates across all companies
4. If no duplicate found, account is created immediately
5. Employee receives invitation email with login credentials
6. Employee can login and complete any missing information

**Important**: National ID number is mandatory for duplicate detection.

#### Method 2: Employee Self-Registration (Good for Open Applications)

**When to Use**:
- Open job positions
- Allowing candidates to apply
- Less urgent hiring

**Process**:
1. Employee registers themselves using your company code
2. System checks for duplicates
3. Registration goes into "Pending Approval" status
4. You review the application
5. You approve and assign employment details
6. Employee receives approval notification
7. Employee can now login and complete profile

---

### Step 3: Managing Pending Approvals

If using Method 2 (self-registration):

1. Check pending employee registrations regularly
2. Review employee information
3. Verify identity and credentials
4. Approve or reject applications
5. Assign department, position, and employment details for approved employees

---

### Step 4: Company Profile Management

You can update your company information anytime:
- Company name
- Industry sector
- Contact information
- Address
- Company size

**Note**: Business registration number cannot be changed after initial registration.

---

## Employee Guide

### Step 1: Getting Access

You have **two ways** to get an account:

#### Option A: Your Employer Creates Your Account
1. Your employer adds you to the system
2. You receive an invitation email
3. Email contains your login credentials
4. Login and complete your profile

#### Option B: Self-Registration
1. Get your company's registration code from HR
2. Register yourself on the platform
3. Provide required information including national ID
4. Wait for employer approval
5. Receive approval notification
6. Login and complete your profile

---

### Step 2: First Login

**What You Need**:
- Your email address (used during registration)
- Your password

**After Login**:
- You receive access tokens (keep these secure)
- System checks if your profile is complete
- You may be prompted to complete missing information

---

### Step 3: Completing Your Profile

**Why It's Important**:
- Ensures accurate payroll processing
- Required for official documentation
- Needed for emergency situations

**Information You'll Provide**:
- Personal details (name, date of birth, gender)
- Contact information (phone, address)
- Emergency contact details
- Marital status
- National ID number

**What's Synced to Central Registry**:
When you update your profile, the following information is automatically synchronized to the central employee registry:
- Full name
- National ID number
- Email address
- Phone number
- Date of birth
- Gender
- Address
- Emergency contact information

This ensures your core information is tracked across the system for duplicate prevention.

---

### Step 4: Checking Profile Completion

You can check your profile completion status anytime:
- See what percentage of your profile is complete
- View list of missing required fields
- View list of optional fields not filled

**Aim for 100%**: A complete profile ensures you receive all benefits and avoid processing delays.

---

## Key Features

### 1. Cross-Institutional Duplicate Detection

**What It Does**:
Prevents employees from being registered at multiple companies simultaneously.

**How It Works**:
- Every employee creation checks the central registry
- National ID number must be unique across ALL companies
- If duplicate found, system shows which company employee is already registered with
- Employer can contact the other company to verify employment status

**Benefits**:
- Prevents fraud
- Ensures data integrity
- Protects both employers and employees
- Maintains accurate employment records

---

### 2. Automatic Database Provisioning

**What It Does**:
When an employer registers, the system automatically creates a dedicated database.

**How It Works**:
1. Employer completes registration
2. System generates unique database name
3. Database is created in PostgreSQL
4. All necessary tables are created
5. Employer can immediately start adding employees

**Benefits**:
- No manual setup required
- Instant operational readiness
- Complete data isolation between companies
- Scalable architecture

---

### 3. Profile Synchronization

**What It Does**:
Keeps employee data synchronized between company database and central registry.

**When It Syncs**:
- When employer creates employee account
- After employee self-registration is approved
- When employee updates their profile
- When employer updates employee information

**What Gets Synced**:
- Personal information
- Contact details
- Emergency contacts
- National ID verification

**Benefits**:
- Duplicate detection always has latest data
- Cross-institutional tracking stays accurate
- Data consistency maintained

---

### 4. Secure Authentication

**What It Does**:
Provides secure access using JWT (JSON Web Tokens).

**Token Types**:
- **Access Token**: Valid for 60 minutes, used for API calls
- **Refresh Token**: Valid for 7 days, used to get new access tokens

**Security Features**:
- Passwords are encrypted
- Tokens expire automatically
- Each company's data is isolated
- Role-based access control

---

## Frequently Asked Questions

### For Employers

**Q: Can I change my business registration number after registration?**  
A: No, the business registration number is permanent and cannot be changed as it's used to create your tenant database name.

**Q: What happens if I try to add an employee who already exists at another company?**  
A: The system will detect the duplicate and show you which company the employee is registered with. You'll need to contact that company to verify employment status before proceeding.

**Q: How many employees can I add?**  
A: There's no limit. Your tenant database scales with your needs.

**Q: Can employees see data from other employees?**  
A: No, employees can only access their own profile information. Only employers can see all employee data.

**Q: What if I forget my password?**  
A: Use the password reset functionality (contact system administrator for assistance).

---

### For Employees

**Q: Why is my national ID number required?**  
A: National ID is used to prevent duplicate registrations across different companies and ensure data integrity.

**Q: Can I work for multiple companies in this system?**  
A: Currently, the system is designed for single-employer registration. If you change employers, the new company must coordinate with your previous employer.

**Q: What information can my employer see?**  
A: Your employer can see all information in your employee profile as they manage your employment records.

**Q: Can I update my information after my profile is complete?**  
A: Yes, you can update most personal information. Changes to employment details (position, salary, etc.) must be made by your employer.

**Q: What happens to my data if I leave the company?**  
A: Your employer controls your employment data. Typically, your account would be deactivated but your records remain for compliance and historical purposes.

---

### Technical Questions

**Q: Is my data secure?**  
A: Yes. Each company has isolated database space, all passwords are encrypted, and authentication uses secure JWT tokens.

**Q: How does the central registry work?**  
A: The central registry is a separate database that stores core employee information (name, national ID, email) for duplicate detection. Your detailed employment data stays in your employer's database.

**Q: What happens if the system detects a duplicate?**  
A: The system prevents the registration and shows details about where the employee is already registered. This protects both employers and employees from fraudulent duplicate registrations.

**Q: Can the system be accessed offline?**  
A: No, this is a web-based system that requires internet connection.

---

## Troubleshooting

### Common Issues and Solutions

#### "Duplicate employee detected at another institution"

**Problem**: Trying to register an employee who already exists in the system.

**Solutions**:
1. Verify the national ID number is correct
2. Contact the institution where employee is registered
3. Confirm employment status with that institution
4. If employee has left previous job, previous employer must update their records
5. Wait for central registry to sync before retrying

---

#### "National ID number is required"

**Problem**: Trying to create employee without national ID.

**Solution**:
- National ID is mandatory for all employee registrations
- Obtain valid national ID from employee before proceeding
- This requirement ensures duplicate detection works properly

---

#### "Invalid employer code"

**Problem**: Employee self-registration with wrong company code.

**Solutions**:
1. Verify employer code with HR department
2. Check for typos (codes are case-sensitive)
3. Ensure you have the current active code
4. Contact employer to confirm correct code

---

#### "Token expired" or "Authentication failed"

**Problem**: Access token has expired (after 60 minutes).

**Solutions**:
1. Use refresh token to get new access token
2. If refresh token expired, login again
3. Store tokens securely for future use
4. Set up automatic token refresh in your application

---

#### "Department does not exist"

**Problem**: Trying to assign employee to non-existent department.

**Solutions**:
1. Create the department first in the system
2. Verify department ID is correct
3. Ensure you're using the right tenant database

---

#### "Employee registration pending approval"

**Problem**: Employee self-registered but can't login.

**Solution**:
- This is normal for self-registration (Method 2)
- Wait for employer approval
- Check email for approval notification
- Contact HR if delayed beyond expected time

---

#### "Profile completion required"

**Problem**: System indicates profile is incomplete.

**Solutions**:
1. Check profile completion status endpoint
2. Fill in all required fields
3. Review list of missing information
4. Update profile with complete information
5. Verify changes were saved successfully

---

## Best Practices

### For Employers

1. **Verify National IDs**: Always verify national ID numbers before creating employee accounts
2. **Use Method 1 for Bulk**: When hiring multiple employees, use employer-created accounts (Method 1)
3. **Review Pending Regularly**: Check pending approvals daily if using self-registration
4. **Keep Company Info Updated**: Maintain accurate company information for compliance
5. **Secure Your Credentials**: Never share your employer account access
6. **Document Your Process**: Maintain internal documentation of your employee onboarding workflow

### For Employees

1. **Complete Your Profile**: Fill out all information as soon as possible
2. **Keep Info Updated**: Update your profile when contact details change
3. **Secure Your Login**: Use a strong password and keep it confidential
4. **Save Your Tokens**: If using API directly, securely store your access tokens
5. **Verify Information**: Review your profile regularly for accuracy
6. **Report Issues Promptly**: Contact HR immediately if you notice any discrepancies

---

## System Workflow Diagrams

### Employer Registration Flow
```
Start
  ↓
Submit Company Information
  ↓
System Validates Data
  ↓
Create Tenant Database
  ↓
Generate Access Tokens
  ↓
Employer Can Login & Add Employees
```

### Employee Creation (Method 1) Flow
```
Employer Creates Employee Account
  ↓
Check Central Registry for Duplicates
  ↓
Duplicate Found? → YES → Show Error & Institution
  ↓ NO
Create Employee in Tenant DB
  ↓
Sync to Central Registry
  ↓
Send Invitation Email
  ↓
Employee Logs In & Completes Profile
```

### Employee Self-Registration (Method 2) Flow
```
Employee Submits Registration
  ↓
Check Central Registry for Duplicates
  ↓
Duplicate Found? → YES → Show Error
  ↓ NO
Create Employee (Status: Pending)
  ↓
Notify Employer
  ↓
Employer Reviews & Approves
  ↓
Sync to Central Registry
  ↓
Notify Employee
  ↓
Employee Logs In & Completes Profile
```

---

## Additional Resources

- **Employer Account Creation Guide**: EMPLOYER_ACCOUNT_CREATION.md
- **Employee Account Creation Guide**: EMPLOYEE_ACCOUNT_CREATION.md
- **API Documentation**: README_API.md
- **General README**: README.md

---

## Support

For technical support or questions:
- Review this manual and additional documentation
- Check the troubleshooting section
- Contact your system administrator
- Review API documentation for technical details

---

## Summary

This HR System provides:
- **Secure multi-tenant architecture** for data privacy
- **Cross-institutional duplicate detection** to prevent fraud
- **Two flexible employee onboarding methods** for different scenarios
- **Automatic database provisioning** for instant readiness
- **Profile synchronization** for data consistency
- **Comprehensive security** with JWT authentication

Whether you're an employer managing your workforce or an employee accessing your information, this system provides the tools you need for efficient HR management.

---

**Version**: 1.0  
**Last Updated**: December 17, 2025  
**System**: Django 5.2.9 Multi-tenant HR Application
