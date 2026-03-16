from rest_framework.decorators import api_view
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import CvExtract
from .services import CVExtractionError, extract_cv_intelligence

@api_view(["GET"])
def health(request):
    return Response({"status": "ok", "message": "Django API is live"})


class CvExtractView(APIView):
    parser_classes = (MultiPartParser, FormParser)

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
        }

        low_confidence = result.structured_cv.get("confidence_score", 0) < 40
        if low_confidence:
            response_payload["status"] = "low_confidence"
            response_payload["message"] = "CV formatting may prevent accurate extraction."

        return Response(response_payload, status=201)


def _parse_bool(value, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off"}