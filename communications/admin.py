from django.contrib import admin

from .models import (
    Communication,
    CommunicationAttachment,
    CommunicationAuditLog,
    CommunicationComment,
    CommunicationRecipient,
    CommunicationResponse,
    CommunicationTarget,
    CommunicationTemplate,
    CommunicationTemplateVersion,
    CommunicationVersion,
)


admin.site.register(Communication)
admin.site.register(CommunicationVersion)
admin.site.register(CommunicationTarget)
admin.site.register(CommunicationRecipient)
admin.site.register(CommunicationComment)
admin.site.register(CommunicationResponse)
admin.site.register(CommunicationAttachment)
admin.site.register(CommunicationAuditLog)
admin.site.register(CommunicationTemplate)
admin.site.register(CommunicationTemplateVersion)
