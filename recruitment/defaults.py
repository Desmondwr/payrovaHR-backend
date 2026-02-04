RECRUITMENT_DEFAULTS = {
    "schema_version": 1,
    "settings": {
        "job_publish_scope": "INTERNAL_ONLY",
        "public_applications_enabled": False,
        "internal_applications_enabled": True,
        "public_apply_requires_login": False,
        "internal_apply_requires_login": True,
        "email_automation_enabled": True,
        "default_ack_email_subject": "Application received",
        "default_ack_email_body": (
            "Hi {{candidate_name}},\n\n"
            "Thanks for applying to {{company_name}}. "
            "We have received your application and will review it shortly.\n\n"
            "Regards,\n{{company_name}} HR"
        ),
        "cv_allowed_extensions": ["pdf", "doc", "docx"],
        "cv_max_file_size_mb": 10,
        "public_apply_rate_limit_requests": 20,
        "public_apply_rate_limit_window_seconds": 3600,
        "public_apply_captcha_enabled": False,
        "public_apply_spam_check_enabled": True,
        "public_apply_honeypot_enabled": True,
        "duplicate_application_window_days": 30,
        "duplicate_application_action": "BLOCK",
        "integration_interview_scheduling_enabled": False,
        "integration_offers_esign_enabled": False,
        "integration_resume_ocr_enabled": False,
        "integration_job_board_ingest_enabled": False,
    },
    "application_fields": [
        {
            "key": "full_name",
            "label": "Full name",
            "type": "text",
            "required": True,
            "enabled": True,
        },
        {
            "key": "email",
            "label": "Email",
            "type": "email",
            "required": True,
            "enabled": True,
        },
        {
            "key": "phone",
            "label": "Phone",
            "type": "phone",
            "required": False,
            "enabled": True,
        },
        {
            "key": "cv",
            "label": "Resume/CV",
            "type": "file",
            "required": True,
            "enabled": True,
        },
        {
            "key": "linkedin",
            "label": "LinkedIn",
            "type": "url",
            "required": False,
            "enabled": True,
        },
        {
            "key": "intro",
            "label": "Introduction",
            "type": "textarea",
            "required": False,
            "enabled": True,
        },
    ],
    "custom_questions": [],
    "stages": [
        {
            "name": "New",
            "sequence": 1,
            "scope": "GLOBAL",
            "auto_email_enabled": True,
            "auto_email_subject": "Application received",
            "auto_email_body": (
                "Hi {{candidate_name}},\n\n"
                "Thanks for applying to {{company_name}}. "
                "We have received your application and will review it shortly.\n\n"
                "Regards,\n{{company_name}} HR"
            ),
            "is_folded": False,
        },
        {
            "name": "Initial Qualification",
            "sequence": 2,
            "scope": "GLOBAL",
            "auto_email_enabled": False,
            "is_folded": False,
        },
        {
            "name": "First Interview",
            "sequence": 3,
            "scope": "GLOBAL",
            "auto_email_enabled": False,
            "is_folded": False,
        },
        {
            "name": "Second Interview",
            "sequence": 4,
            "scope": "GLOBAL",
            "auto_email_enabled": False,
            "is_folded": False,
        },
        {
            "name": "Contract Proposal",
            "sequence": 5,
            "scope": "GLOBAL",
            "auto_email_enabled": False,
            "is_folded": False,
            "is_contract_stage": True,
        },
        {
            "name": "Contract Signed",
            "sequence": 6,
            "scope": "GLOBAL",
            "auto_email_enabled": False,
            "is_folded": True,
            "is_hired_stage": True,
        },
    ],
}
