from django.conf import settings
from django.core import signing
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from datetime import timedelta
from hashlib import sha256
import secrets
from .models import (
    User,
    Doctor,
    SeedLevel,
    DoctorReport,
    FullReport,
)
from .models import GameApiTokenSession
from .serializers import (
    UserSerializer,
    DoctorSerializer,
    SeedLevelSerializer,
    DoctorReportSerializer,
    FullReportSerializer,
)

ACCESS_TOKEN_SALT = "gameapi.access_token"


def require_admin_access(request):
    if not request.user or not request.user.is_authenticated:
        return Response(
            {"error": "admin authentication required"},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    if not request.user.is_staff:
        return Response(
            {"error": "admin privileges required"},
            status=status.HTTP_403_FORBIDDEN,
        )

    return None


def get_game_api_bootstrap_token(request):
    return (
        request.headers.get("X-Game-Api-Key")
        or request.data.get("api_key")
        or request.query_params.get("api_key")
    )


def get_bearer_token(request):
    authorization = request.headers.get("Authorization", "")
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        return ""

    return authorization[len(prefix):].strip()


def get_refresh_token_from_request(request):
    return (
        request.data.get("refresh_token")
        or request.headers.get("X-Refresh-Token")
        or request.query_params.get("refresh_token")
    )


def hash_token(raw_token):
    return sha256(raw_token.encode("utf-8")).hexdigest()


def get_access_token_expiry():
    return timezone.now() + timedelta(
        seconds=settings.GAME_API_ACCESS_TOKEN_LIFETIME_SECONDS
    )


def get_refresh_token_expiry():
    return timezone.now() + timedelta(
        seconds=settings.GAME_API_REFRESH_TOKEN_LIFETIME_SECONDS
    )


def build_access_token(session, expires_at):
    payload = {
        "type": "game_access",
        "session_id": session.id,
        "exp": int(expires_at.timestamp()),
    }
    return signing.dumps(payload, salt=ACCESS_TOKEN_SALT)


def create_token_payload(session):
    access_expires_at = get_access_token_expiry()
    refresh_token = secrets.token_urlsafe(48)
    session.refresh_token_hash = hash_token(refresh_token)
    session.expires_at = get_refresh_token_expiry()
    session.revoked_at = None
    session.save(update_fields=["refresh_token_hash", "expires_at", "revoked_at", "last_used_at"])

    return {
        "access_token": build_access_token(session, access_expires_at),
        "access_token_expires_at": access_expires_at.isoformat(),
        "expires_in": settings.GAME_API_ACCESS_TOKEN_LIFETIME_SECONDS,
        "refresh_token": refresh_token,
        "refresh_token_expires_at": session.expires_at.isoformat(),
        "token_type": "Bearer",
    }


def validate_access_token(access_token):
    if not access_token:
        return None

    try:
        payload = signing.loads(access_token, salt=ACCESS_TOKEN_SALT)
    except signing.BadSignature:
        return None

    if payload.get("type") != "game_access":
        return None

    if int(payload.get("exp", 0)) <= int(timezone.now().timestamp()):
        return None

    session_id = payload.get("session_id")
    if not session_id:
        return None

    session = GameApiTokenSession.objects.filter(id=session_id).first()
    if not session or not session.is_active():
        return None

    session.touch()
    return session


def require_bootstrap_token(request):
    expected_token = settings.GAME_API_WRITE_TOKEN
    if not expected_token:
        return Response(
            {"error": "GAME_API_WRITE_TOKEN is not configured"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    provided_token = str(get_game_api_bootstrap_token(request) or "")
    if secrets.compare_digest(provided_token, expected_token):
        return None

    return Response(
        {"error": "valid bootstrap API key required"},
        status=status.HTTP_401_UNAUTHORIZED,
    )


def is_admin_request(request):
    return bool(
        request.user
        and request.user.is_authenticated
        and request.user.is_staff
    )


def require_game_api_access_token(request):
    if is_admin_request(request):
        return None

    session = validate_access_token(get_bearer_token(request))
    if session:
        request.game_api_session = session
        return None

    return Response(
        {"error": "admin authentication or valid access token required"},
        status=status.HTTP_401_UNAUTHORIZED,
    )


def require_game_write_token(request):
    return require_game_api_access_token(request)


def parse_age(age_value):
    if age_value in (None, ""):
        return None

    try:
        return int(age_value)
    except (TypeError, ValueError):
        return "invalid"


def get_doctor_from_request(request):
    doctor_id = request.data.get("doctor_id")
    if doctor_id not in (None, ""):
        try:
            doctor = Doctor.objects.get(id=int(doctor_id))
        except (TypeError, ValueError, Doctor.DoesNotExist):
            return None, str(doctor_id)

        return doctor, None

    doctor_token = (
        request.data.get("doctor_token")
        or request.data.get("doctor_key")
    )

    if not doctor_token:
        doctor_ids = request.data.get("doctors")
        if isinstance(doctor_ids, list) and doctor_ids:
            try:
                doctor = Doctor.objects.get(id=int(doctor_ids[0]))
            except (TypeError, ValueError, Doctor.DoesNotExist):
                return None, str(doctor_ids[0])

            return doctor, None

        return None, None

    try:
        doctor = Doctor.objects.get(token=doctor_token)
    except Doctor.DoesNotExist:
        return None, doctor_token

    return doctor, None


@api_view(["POST"])
def create_game_api_token(request):
    bootstrap_response = require_bootstrap_token(request)
    if bootstrap_response:
        return bootstrap_response

    session = GameApiTokenSession.objects.create(
        device_uuid=str(request.data.get("uuid", "")).strip(),
        user_agent=request.headers.get("User-Agent", "")[:255],
        refresh_token_hash=hash_token(secrets.token_urlsafe(48)),
        expires_at=get_refresh_token_expiry(),
    )
    payload = create_token_payload(session)
    payload["session_id"] = session.id
    return Response(payload, status=status.HTTP_201_CREATED)


@api_view(["POST"])
def refresh_game_api_token(request):
    refresh_token = str(get_refresh_token_from_request(request) or "").strip()
    if not refresh_token:
        return Response({"error": "refresh_token required"}, status=400)

    refresh_token_hash = hash_token(refresh_token)
    with transaction.atomic():
        session = (
            GameApiTokenSession.objects.select_for_update()
            .filter(refresh_token_hash=refresh_token_hash)
            .first()
        )

        if not session or not session.is_active():
            return Response({"error": "refresh token is invalid or expired"}, status=401)

        payload = create_token_payload(session)
    payload["session_id"] = session.id
    return Response(payload)


@api_view(['GET', 'POST', 'DELETE'])
def user_api(request, id=None):
    if request.method == "GET":
        access_response = require_game_api_access_token(request)
        if access_response:
            return access_response
    elif request.method == "DELETE":
        admin_response = require_admin_access(request)
        if admin_response:
            return admin_response

    if request.method == 'GET':
        if id:
            try:
                user = User.objects.get(id=id)
                return Response(UserSerializer(user).data)
            except User.DoesNotExist:
                return Response({"error": "User not found"}, status=404)

        token_filter = request.query_params.get("token")
        if token_filter:
            user = User.objects.filter(token=token_filter).order_by("id").first()
            if not user:
                return Response({"error": "User not found"}, status=404)
            return Response(UserSerializer(user).data)

        if not is_admin_request(request):
            return Response(
                {"error": "filtered lookup required for access token usage"},
                status=status.HTTP_403_FORBIDDEN,
            )

        users = User.objects.all()
        return Response(UserSerializer(users, many=True).data)

    if request.method == 'POST':
        print("METHOD:", request.method)
        print("PATH:", request.path)
        print("DATA:", request.data)

        token_response = require_game_write_token(request)
        if token_response:
            print("AUTH_ERROR:", getattr(token_response, "data", None))
            return token_response

        token = request.data.get("token")
        uuid = request.data.get("uuid")
        age = parse_age(request.data.get("age"))
        doctor, invalid_doctor_token = get_doctor_from_request(request)
        print(
            "PARSED_VALUES:",
            {
                "token": token,
                "uuid": uuid,
                "age": age,
                "doctor": getattr(doctor, "id", None),
                "invalid_doctor_token": invalid_doctor_token,
            },
        )

        if not token:
            print("POST_USER_ERROR:", "token required")
            return Response({"error": "token required"}, status=400)

        if age == "invalid":
            print("POST_USER_ERROR:", "age must be an integer")
            return Response({"error": "age must be an integer"}, status=400)

        if invalid_doctor_token:
            print("POST_USER_ERROR:", "doctor token does not exist")
            return Response({"error": "doctor token does not exist"}, status=404)

        if token == "guest":
            print("USER_BRANCH:", "guest")
            try:
                user = User.objects.get(token="guest")
                print("GUEST_FOUND:", {"id": user.id, "uuid": user.uuid, "age": user.age})
            except User.DoesNotExist:
                print("GUEST_CREATE_PAYLOAD:", {"token": "guest", "uuid": None, "age": age})
                user = User.objects.create(token="guest", uuid=None, age=age)
                print("GUEST_CREATED:", {"id": user.id})

            if age is not None:
                user.age = age
                user.save(update_fields=["age"])
                print("GUEST_AGE_UPDATED:", {"id": user.id, "age": user.age})

            if doctor:
                print("GUEST_ADD_DOCTOR:", {"user_id": user.id, "doctor_id": doctor.id})
                user.doctors.add(doctor)

            response_data = UserSerializer(user).data
            print("RESPONSE_DATA:", response_data)
            return Response(response_data)

        if not uuid:
            print("POST_USER_ERROR:", "uuid required")
            return Response({"error": "uuid required"}, status=400)

        user = User.objects.filter(token=token).order_by("id").first()
        created = user is None
        print("USER_LOOKUP:", {"created": created, "existing_user_id": getattr(user, "id", None)})

        if created:
            print("USER_CREATE_PAYLOAD:", {"token": token, "uuid": uuid, "age": age})
            user = User.objects.create(
                token=token,
                uuid=uuid,
                age=age,
            )
            print("USER_CREATED:", {"id": user.id})
        else:
            fields_to_update = []

            if user.uuid != uuid:
                user.uuid = uuid
                fields_to_update.append("uuid")

            if age is not None and user.age != age:
                user.age = age
                fields_to_update.append("age")

            if fields_to_update:
                print("USER_UPDATE_FIELDS:", {"id": user.id, "fields": fields_to_update})
                user.save(update_fields=fields_to_update)

        if doctor:
            print("USER_ADD_DOCTOR:", {"user_id": user.id, "doctor_id": doctor.id})
            user.doctors.add(doctor)

        response_data = UserSerializer(user).data
        print("RESPONSE_DATA:", response_data)
        return Response(response_data)

    if request.method == 'DELETE':
        try:
            user = User.objects.get(id=id)
            user.delete()
            return Response({"message": "User deleted"})
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=404)

@api_view(['GET', 'POST', 'DELETE'])
def doctor_api(request, id=None):
    if request.method == "GET":
        access_response = require_game_api_access_token(request)
        if access_response:
            return access_response
    else:
        admin_response = require_admin_access(request)
        if admin_response:
            return admin_response

    if request.method == 'GET':
        if id:
            try:
                obj = Doctor.objects.get(id=id)
                return Response(DoctorSerializer(obj).data)
            except Doctor.DoesNotExist:
                return Response({"error": "Doctor not found"}, status=404)

        token_filter = request.query_params.get("token")
        if token_filter:
            obj = Doctor.objects.filter(token=token_filter).first()
            if not obj:
                return Response({"error": "Doctor not found"}, status=404)
            return Response(DoctorSerializer(obj).data)

        if not is_admin_request(request):
            return Response(
                {"error": "filtered lookup required for access token usage"},
                status=status.HTTP_403_FORBIDDEN,
            )

        return Response(DoctorSerializer(Doctor.objects.all(), many=True).data)

    if request.method == 'POST':
        serializer = DoctorSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors)

    if request.method == 'DELETE':
        try:
            obj = Doctor.objects.get(id=id)
            obj.delete()
            return Response({"message": "Doctor deleted"})
        except Doctor.DoesNotExist:
            return Response({"error": "Doctor not found"}, status=404)


@api_view(['GET', 'POST', 'DELETE'])
def seed_api(request, id=None):
    if request.method == "POST":
        token_response = require_game_write_token(request)
        if token_response:
            return token_response
    else:
        admin_response = require_admin_access(request)
        if admin_response:
            return admin_response

    if request.method == 'GET':
        if id:
            try:
                obj = SeedLevel.objects.get(id=id)
                return Response(SeedLevelSerializer(obj).data)
            except SeedLevel.DoesNotExist:
                return Response({"error": "Seed not found"}, status=404)
        return Response(SeedLevelSerializer(SeedLevel.objects.all(), many=True).data)

    if request.method == 'POST':
        serializer = SeedLevelSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors)

    if request.method == 'DELETE':
        try:
            obj = SeedLevel.objects.get(id=id)
            obj.delete()
            return Response({"message": "Seed deleted"})
        except SeedLevel.DoesNotExist:
            return Response({"error": "Seed not found"}, status=404)

@api_view(['GET', 'POST', 'DELETE'])
def doctor_report_api(request, id=None):
    if request.method in {"GET", "DELETE"}:
        admin_response = require_admin_access(request)
        if admin_response:
            return admin_response

    if request.method == 'GET':
        if id:
            try:
                obj = DoctorReport.objects.get(id=id)
                return Response(DoctorReportSerializer(obj).data)
            except DoctorReport.DoesNotExist:
                return Response({"error": "Doctor report not found"}, status=404)
        return Response(DoctorReportSerializer(DoctorReport.objects.all(), many=True).data)

    if request.method == 'POST':
        print("DATA:", request.data, flush=True)
        print("FILES:", request.FILES, flush=True)
        print("FILE_KEYS:", list(request.FILES.keys()), flush=True)

        token_response = require_game_write_token(request)
        if token_response:
            return token_response

        serializer = DoctorReportSerializer(data=request.data)
        is_valid = serializer.is_valid()
        print("IS_VALID:", is_valid, flush=True)
        print("ERRORS:", serializer.errors, flush=True)
        if is_valid:
            try:
                validated_data = serializer.validated_data
                print("VALIDATED_KEYS:", list(validated_data.keys()), flush=True)
                print("VALIDATED_USER:", validated_data.get("user"), flush=True)
                print("VALIDATED_SESSION_ID:", validated_data.get("session_id"), flush=True)
                print("VALIDATED_SEED:", validated_data.get("seed"), flush=True)
                print("VALIDATED_FILE:", validated_data.get("file"), flush=True)
                print("VALIDATED_DOCTORS:", validated_data.get("doctors"), flush=True)
                incoming_file = validated_data.get("file")
                print(
                    "INCOMING_FILE:",
                    incoming_file.name if incoming_file else None,
                    flush=True,
                )
            except Exception as e:
                import traceback

                traceback.print_exc()
                print("DOCTOR_REPORT_VALIDATED_DATA_ERROR:", repr(e), flush=True)
                raise
            try:
                obj, created = DoctorReport.objects.update_or_create(
                    user=validated_data["user"],
                    session_id=validated_data["session_id"],
                    defaults={
                        "seed": validated_data["seed"],
                        "file": validated_data["file"],
                    },
                )
                print("UPSERT_CREATED:", created, flush=True)
                print("OBJ_ID:", obj.id, flush=True)
                print("SETTING_DOCTORS:", validated_data["doctors"], flush=True)
                print("DOCTORS_SOURCE:", validated_data.get("doctors"), flush=True)
                obj.doctors.set(validated_data["doctors"])
            except Exception as e:
                import traceback

                traceback.print_exc()
                print("DOCTOR_REPORT_ERROR:", repr(e), flush=True)
                raise
            print("SAVED_ID:", obj.id, flush=True)
            print("SAVED_FILE:", obj.file.name if obj.file else None, flush=True)
            print(
                "UPDATED_FILE_AFTER_SAVE:",
                obj.file.name if obj.file else None,
                flush=True,
            )
            try:
                response_data = DoctorReportSerializer(obj).data
                print("RESPONSE_DATA:", response_data, flush=True)
            except Exception as e:
                import traceback

                traceback.print_exc()
                print("DOCTOR_REPORT_RESPONSE_ERROR:", repr(e), flush=True)
                raise
            return Response(response_data)
        return Response(serializer.errors, status=400)

    if request.method == 'DELETE':
        try:
            obj = DoctorReport.objects.get(id=id)
            obj.delete()
            return Response({"message": "Doctor report deleted"})
        except DoctorReport.DoesNotExist:
            return Response({"error": "Doctor report not found"}, status=404)

@api_view(['GET', 'POST', 'DELETE'])
def full_report_api(request, id=None):
    if request.method in {"GET", "DELETE"}:
        admin_response = require_admin_access(request)
        if admin_response:
            return admin_response

    if request.method == 'GET':
        if id:
            try:
                obj = FullReport.objects.get(id=id)
                return Response(FullReportSerializer(obj).data)
            except FullReport.DoesNotExist:
                return Response({"error": "Full report not found"}, status=404)
        return Response(FullReportSerializer(FullReport.objects.all(), many=True).data)

    if request.method == 'POST':
        print("DATA:", request.data)
        print("FILES:", request.FILES)
        print("FILE_KEYS:", list(request.FILES.keys()))

        token_response = require_game_write_token(request)
        if token_response:
            return token_response

        serializer = FullReportSerializer(data=request.data)
        is_valid = serializer.is_valid()
        print("IS_VALID:", is_valid)
        print("ERRORS:", serializer.errors)
        if is_valid:
            print("VALIDATED_DATA:", serializer.validated_data)
            incoming_file = serializer.validated_data.get("file")
            print(
                "INCOMING_FILE:",
                incoming_file.name if incoming_file else None,
                flush=True,
            )
            obj, created = FullReport.objects.update_or_create(
                user=serializer.validated_data["user"],
                session_id=serializer.validated_data["session_id"],
                defaults={
                    "file": serializer.validated_data["file"],
                },
            )
            print("UPSERT_CREATED:", created)
            print("SAVED_ID:", obj.id)
            print("SAVED_FILE:", obj.file.name if obj.file else None)
            print(
                "UPDATED_FILE_AFTER_SAVE:",
                obj.file.name if obj.file else None,
                flush=True,
            )
            return Response(FullReportSerializer(obj).data)
        return Response(serializer.errors, status=400)

    if request.method == 'DELETE':
        try:
            obj = FullReport.objects.get(id=id)
            obj.delete()
            return Response({"message": "Full report deleted"})
        except FullReport.DoesNotExist:
            return Response({"error": "Full report not found"}, status=404)
