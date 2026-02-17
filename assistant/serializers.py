from rest_framework import serializers


class AssistantHistoryItemSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=["user", "assistant"])
    content = serializers.CharField(max_length=2000, allow_blank=False, trim_whitespace=True)


class AssistantChatRequestSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=2000, allow_blank=False, trim_whitespace=True)
    interaction_type = serializers.ChoiceField(
        choices=["chat", "nudge"],
        required=False,
        default="chat",
    )
    portal_mode = serializers.ChoiceField(
        choices=["admin", "employer", "employee"],
        required=False,
        allow_null=True,
    )
    page_path = serializers.CharField(max_length=255, required=False, allow_blank=True)
    locale = serializers.CharField(max_length=20, required=False, allow_blank=True)
    history = AssistantHistoryItemSerializer(many=True, required=False)

    def validate_history(self, value):
        if len(value) > 20:
            raise serializers.ValidationError("History length cannot exceed 20 messages.")
        return value
