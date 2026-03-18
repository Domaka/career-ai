from django.contrib.auth import authenticate, get_user_model
from rest_framework.decorators import api_view
from rest_framework.authentication import TokenAuthentication
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.authtoken.models import Token

from .models import CvAnalysis, CvExtract
from .services import CVExtractionError, extract_cv_intelligence
from .services.cv_analysis import build_profile_analysis

User = get_user_model()

@api_view(["GET"])
def health(request):
    return Response({"status": "ok", "message": "Django API is live"})


class CvExtractView(APIView):
    parser_classes = (MultiPartParser, FormParser)
    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        cv_file = request.FILES.get("cv_file")
        profile_id = request.data.get("profile_id")
        target_role = request.data.get("target_role")
        use_llm = _parse_bool(request.data.get("use_llm"), default=True)
        auto_learn = _parse_bool(request.data.get("auto_learn"), default=True)

        if cv_file is None:
            return Response({"error": "cv_file is required"}, status=400)

        if profile_id is None:
            return Response({"error": "profile_id is required"}, status=400)

        try:
            profile_id_int = int(profile_id)
        except (TypeError, ValueError):
            return Response({"error": "profile_id must be an integer"}, status=400)

        try:
            result = extract_cv_intelligence(
                cv_file=cv_file,
                target_role=target_role,
                use_llm=use_llm,
                auto_learn=auto_learn,
            )
        except CVExtractionError as exc:
            return Response({"error": exc.message}, status=exc.status_code)

        cv_extract = CvExtract.objects.create(
            profile_id=profile_id_int,
            raw_text=result.raw_text,
            clean_text=result.clean_text,
            structured_json=result.structured_cv,
            derived_metrics=result.derived_metrics,
            page_count=result.page_count,
            career_level_estimate=result.structured_cv.get("career_level_estimate", "unknown"),
            confidence_score=result.structured_cv.get("confidence_score", 0),
        )

        analysis_result = build_profile_analysis(
            structured_cv=result.structured_cv,
            derived_metrics=result.derived_metrics,
            target_role=target_role,
            use_llm=use_llm,
        )

        analysis_payload = analysis_result["analysis"]
        cv_analysis = CvAnalysis.objects.create(
            profile_id=profile_id_int,
            cv_extract=cv_extract,
            summary=analysis_payload.get("summary", ""),
            strengths=analysis_payload.get("strengths", []),
            weaknesses=analysis_payload.get("weaknesses", []),
            talent_gaps=analysis_payload.get("talent_gaps", []),
            analysis_json=analysis_payload,
            source=analysis_result.get("source", "rules"),
            fallback_reason=analysis_result.get("fallback_reason", ""),
        )

        response_payload = {
            "profile_id": profile_id_int,
            "extract_id": cv_extract.id,
            "career_level_estimate": result.structured_cv.get("career_level_estimate", "unknown"),
            "confidence_score": result.structured_cv.get("confidence_score", 0),
            "extraction_mode": getattr(result, "extraction_mode", "heuristic"),
            "derived_metrics": result.derived_metrics,
            "structured_cv": result.structured_cv,
            "llm_structured_cv": getattr(result, "llm_structured_cv", None),
            "comparison": getattr(result, "comparison", None),
            "analysis": {
                "analysis_id": cv_analysis.id,
                "source": cv_analysis.source,
                "fallback_reason": cv_analysis.fallback_reason,
                "summary": cv_analysis.summary,
                "strengths": cv_analysis.strengths,
                "weaknesses": cv_analysis.weaknesses,
                "talent_gaps": cv_analysis.talent_gaps,
                "analysis_json": cv_analysis.analysis_json,
            },
        }

        low_confidence = result.structured_cv.get("confidence_score", 0) < 40
        if low_confidence:
            response_payload["status"] = "low_confidence"
            response_payload["message"] = "CV formatting may prevent accurate extraction."

        return Response(response_payload, status=201)


class RegisterView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        username = str(request.data.get("username", "")).strip()
        password = str(request.data.get("password", "")).strip()
        email = str(request.data.get("email", "")).strip()

        if not username or not password:
            return Response({"error": "username and password are required"}, status=400)

        if User.objects.filter(username=username).exists():
            return Response({"error": "username already exists"}, status=400)

        user = User.objects.create_user(
            username=username,
            password=password,
            email=email,
        )
        token, _ = Token.objects.get_or_create(user=user)

        return Response(
            {
                "message": "registration successful",
                "token": token.key,
                "user": {"id": user.id, "username": user.username, "email": user.email},
            },
            status=201,
        )


class LoginView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        username = str(request.data.get("username", "")).strip()
        password = str(request.data.get("password", "")).strip()

        if not username or not password:
            return Response({"error": "username and password are required"}, status=400)

        user = authenticate(request, username=username, password=password)
        if user is None:
            return Response({"error": "invalid credentials"}, status=401)

        token, _ = Token.objects.get_or_create(user=user)
        return Response(
            {
                "message": "login successful",
                "token": token.key,
                "user": {"id": user.id, "username": user.username, "email": user.email},
            }
        )


class LogoutView(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response({"message": "logout successful"})


class MeView(APIView):
    authentication_classes = (TokenAuthentication,)
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        return Response(
            {
                "id": request.user.id,
                "username": request.user.username,
                "email": request.user.email,
            }
        )


def _parse_bool(value, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off"}