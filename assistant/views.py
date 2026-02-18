from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from rest_framework import permissions, status
from rest_framework.views import APIView

from accounts.utils import api_response

from .serializers import AssistantChatRequestSerializer
from .services import generate_assistant_reply


@method_decorator(ratelimit(key="user_or_ip", rate="60/h", method="POST", block=True), name="dispatch")
class AssistantChatView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = AssistantChatRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return api_response(
                success=False,
                message="Invalid assistant request.",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        payload = generate_assistant_reply(request, serializer.validated_data)
        return api_response(
            success=True,
            message="Assistant reply generated.",
            data=payload,
            status=status.HTTP_200_OK,
        )
