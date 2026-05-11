from django.conf import settings
from django.core.files.base import ContentFile
from django.core import signing
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.utils import timezone
from django.utils.text import get_valid_filename
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
    FullReport,
)
from .models import GameApiTokenSession
from .report_charts import (
    ReportChartDependencyError,
    ReportChartError,
    generate_full_report_chart,
)

ACCESS_TOKEN_SALT = "gameapi.access_token"
REPORT_LEVEL_COUNT_WIDTH = 2


def doctor_data(obj):
    return {
        "id": obj.id,
        "last_name": obj.last_name,
        "first_name": obj.first_name,
        "token": obj.token,
        "email": obj.email,
    }


def seed_level_data(obj):
    return {
        "id": obj.id,
        "name": obj.name,
        "file": obj.file.url if obj.file else None,
    }


def user_data(obj):
    doctor = obj.doctors.order_by("-id").first()
    doctors = [doctor_data(doctor_obj) for doctor_obj in obj.doctors.all()]

    return {
        "id": obj.id,
        "token": obj.token,
        "uuid": obj.uuid,
        "birth_year": obj.birth_year,
        "doctors": doctors,
        "latest_doctor_id": doctor.id if doctor else None,
        "latest_doctor_token": doctor.token if doctor else "",
        "doctor_key": doctor.token if doctor else "",
    }


def full_report_data(obj):
    return {
        "id": obj.id,
        "user": obj.user_id,
        "session_id": obj.session_id,
        "file": obj.file.url if obj.file else None,
        "date": obj.date,
        "app_version": obj.app_version,
        "app_version_code": obj.app_version_code,
        "level_generation_version": obj.level_generation_version,
        "client_platform": obj.client_platform,
        "seed_levels": [seed.id for seed in obj.seed_levels.all()],
    }


def request_seed_levels(request):
    for field in ("seed_levels", "seeds", "seed"):
        seed_level_ids = request_data_values(request, field)
        if seed_level_ids:
            break
    else:
        return [], None


    try:
        ids = [int(seed_level_id) for seed_level_id in seed_level_ids]
    except (TypeError, ValueError):
        return [], "invalid"

    seed_levels = list(SeedLevel.objects.filter(id__in=ids))
    if len(seed_levels) != len(set(ids)):
        return [], "missing"

    return seed_levels, None


def request_data_values(request, field):
    if hasattr(request.data, "getlist"):
        values = request.data.getlist(field)
    else:
        value = request.data.get(field)
        values = [] if value in (None, "") else [value]

    parsed_values = []
    for value in values:
        if value in (None, ""):
            continue

        parsed_values.extend(
            item.strip()
            for item in str(value).split(",")
            if item.strip()
        )

    return parsed_values


def dat_report_blocks(text_content):
    lines = [line.strip() for line in text_content.splitlines() if line.strip()]
    if not lines:
        return [], "invalid"

    try:
        level_count = int(lines[0])
    except ValueError:
        return [], "invalid"

    if level_count < 1:
        return [], "invalid"

    try:
        index = 1
        blocks = []
        for level_number in range(level_count):
            block, index = read_dat_level_block(
                lines,
                index,
                level_number,
                level_count,
            )
            blocks.append(block)
    except ValueError:
        return [], "invalid"

    if index != len(lines):
        return [], "invalid"

    return blocks, None


def read_dat_level_block(lines, index, level_number, level_count):
    start = index

    index = consume_dat_line(lines, index, int)
    index = consume_dat_line(lines, index, float)
    index = consume_dat_pair(lines, index, int)
    index = consume_dat_pair(lines, index, int)
    index = consume_dat_visual(lines, index)

    tree_count, index = read_dat_count(lines, index)
    for _tree_index in range(tree_count):
        index = consume_dat_pair(lines, index, int)

    position_count, index = read_dat_count(lines, index)
    for _position_index in range(position_count):
        index = consume_dat_pair(lines, index, float)

    is_last_level = level_number == level_count - 1
    remaining_lines = len(lines) - index
    if remaining_lines >= 2:
        index = consume_dat_line(lines, index, float)
        index = consume_dat_line(lines, index, int)
    elif remaining_lines == 0 and is_last_level:
        pass
    else:
        raise ValueError

    return lines[start:index], index


def consume_dat_line(lines, index, parser):
    if index >= len(lines):
        raise ValueError

    parser(lines[index])
    return index + 1


def consume_dat_pair(lines, index, parser):
    if index >= len(lines):
        raise ValueError

    values = lines[index].split()
    if len(values) != 2:
        raise ValueError

    for value in values:
        parser(value)

    return index + 1


def consume_dat_visual(lines, index):
    if index >= len(lines):
        raise ValueError

    values = lines[index].split()
    if len(values) != 3:
        raise ValueError

    for value in values:
        int(value)

    return index + 1


def read_dat_count(lines, index):
    if index >= len(lines):
        raise ValueError

    count = int(lines[index])
    if count < 0:
        raise ValueError

    return count, index + 1


def uploaded_dat_blocks(uploaded_file):
    try:
        raw_content = uploaded_file.read()
        if hasattr(uploaded_file, "seek"):
            uploaded_file.seek(0)
        text_content = raw_content.decode("utf-8")
        return dat_report_blocks(text_content)
    except (AttributeError, UnicodeDecodeError, ValueError):
        return [], "invalid"


def existing_dat_blocks(obj):
    if not obj.file:
        return [], None

    try:
        with obj.file.open("rb") as file_handle:
            text_content = file_handle.read().decode("utf-8")
            return dat_report_blocks(text_content)
    except (FileNotFoundError, UnicodeDecodeError, ValueError):
        return [], "invalid"


def append_report_dat(obj, current_count, uploaded_blocks):
    if not uploaded_blocks:
        return

    filename = report_dat_filename(obj)
    if not obj.file:
        create_report_dat(obj, filename, uploaded_blocks)
        return

    new_count = current_count + len(uploaded_blocks)
    appended_content = dat_blocks_content(uploaded_blocks, include_count=False)

    with obj.file.open("r+b") as file_handle:
        header = file_handle.readline()
        if not header:
            raise ValueError("The existing report file has no level count.")

        header_text = header.decode("utf-8").rstrip("\r\n")
        new_header_text = format_level_count(new_count, len(header_text))
        if len(new_header_text) > len(header_text):
            raise ValueError(
                "The existing report file level-count header is too short "
                "to append in place."
            )

        file_handle.seek(0)
        file_handle.write(new_header_text.encode("utf-8"))
        file_handle.seek(0, 2)
        if file_handle.tell() > 0:
            file_handle.seek(-1, 2)
            last_byte = file_handle.read(1)
            if last_byte not in (b"\n", b"\r"):
                file_handle.write(b"\n")
            else:
                file_handle.seek(0, 2)
        file_handle.write(appended_content)


def create_report_dat(obj, filename, blocks):
    content = dat_blocks_content(blocks, include_count=True)
    obj.file.save(filename, ContentFile(content), save=False)


def dat_blocks_content(blocks, include_count):
    lines = []
    if include_count:
        lines.append(format_level_count(len(blocks), REPORT_LEVEL_COUNT_WIDTH))

    for block in blocks:
        lines.extend(block)

    if not lines:
        return b""

    return ("\n".join(lines) + "\n").encode("utf-8")


def format_level_count(count, width):
    return str(count).zfill(width)


def report_dat_filename(obj):
    session_id = get_valid_filename(str(obj.session_id or obj.pk or "report"))
    return f"report_{session_id}.dat"


def require_admin_access(request):
    if not request.user or not request.user.is_authenticated:
        return Response(
            {"error": "Please sign in with an admin account to continue."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    if not request.user.is_staff:
        return Response(
            {"error": "This action is reserved for staff accounts."},
            status=status.HTTP_403_FORBIDDEN,
        )

    return None


def bootstrap_token(request):
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


def request_refresh_token(request):
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

    # Refresh tokens are rotated on every call so a stolen old token quickly
    # becomes useless, while the mobile client can keep a short-lived session.
    session.refresh_token_hash = hash_token(refresh_token)
    session.expires_at = get_refresh_token_expiry()
    session.revoked_at = None
    session.save(
        update_fields=[
            "refresh_token_hash",
            "expires_at",
            "revoked_at",
            "last_used_at",
        ]
    )

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
            {"error": "The game API is not ready to accept write requests yet."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    provided_token = str(bootstrap_token(request) or "")
    if secrets.compare_digest(provided_token, expected_token):
        return None

    return Response(
        {"error": "A valid bootstrap API key is required to create a session."},
        status=status.HTTP_401_UNAUTHORIZED,
    )


def is_admin_request(request):
    return bool(
        request.user
        and request.user.is_authenticated
        and request.user.is_staff
    )


def require_game_access(request):
    if is_admin_request(request):
        return None

    session = validate_access_token(get_bearer_token(request))
    if session:
        request.game_api_session = session
        return None

    return Response(
        {"error": "Please provide a valid game access token or sign in as an admin."},
        status=status.HTTP_401_UNAUTHORIZED,
    )


def parse_birth_year(birth_year_value):
    if birth_year_value in (None, ""):
        return None

    try:
        return int(birth_year_value)
    except (TypeError, ValueError):
        return "invalid"


def doctor_from_request(request):
    doctor_token = request.data.get("doctor_token")
    if not doctor_token:
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
    refresh_token = str(request_refresh_token(request) or "").strip()
    if not refresh_token:
        return Response(
            {"error": "A refresh_token is required to renew the game session."},
            status=400,
        )

    refresh_token_hash = hash_token(refresh_token)
    with transaction.atomic():
        session = (
            GameApiTokenSession.objects.select_for_update()
            .filter(refresh_token_hash=refresh_token_hash)
            .first()
        )

        if not session or not session.is_active():
            return Response(
                {"error": "This refresh token is invalid or has expired."},
                status=401,
            )

        payload = create_token_payload(session)
    payload["session_id"] = session.id
    return Response(payload)


@api_view(['GET', 'POST', 'DELETE'])
def user_api(request, id=None):
    if request.method == "GET":
        access_response = require_game_access(request)
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
                return Response(user_data(user))
            except User.DoesNotExist:
                return Response(
                    {"error": "No user was found for this id."},
                    status=404,
                )

        token_filter = request.query_params.get("token")
        if token_filter:
            user = User.objects.filter(token=token_filter).order_by("id").first()
            if not user:
                return Response(
                    {"error": "No user was found for this token."},
                    status=404,
                )
            return Response(user_data(user))

        if not is_admin_request(request):
            return Response(
                {
                    "error": (
                        "Use a token filter when looking up users "
                        "from the game client."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        users = User.objects.all()
        return Response([user_data(user) for user in users])

    if request.method == 'POST':
        token_response = require_game_access(request)
        if token_response:
            return token_response

        token = request.data.get("token")
        uuid = request.data.get("uuid")
        birth_year = parse_birth_year(request.data.get("birth_year"))
        doctor, invalid_doctor_token = doctor_from_request(request)

        if not token:
            return Response(
                {"error": "A player token is required to create or update a user."},
                status=400,
            )

        if birth_year == "invalid":
            return Response(
                {"error": "birth_year must be a whole year, for example 2012."},
                status=400,
            )

        if invalid_doctor_token:
            return Response(
                {"error": "No doctor matches the doctor_token sent by the client."},
                status=404,
            )

        if token == "guest":
            # Guest mode is intentionally shared for quick trials.
            try:
                user = User.objects.get(token="guest")
            except User.DoesNotExist:
                user = User.objects.create(
                    token="guest",
                    uuid=None,
                    birth_year=birth_year,
                )

            if birth_year is not None:
                user.birth_year = birth_year
                user.save(update_fields=["birth_year"])

            if doctor:
                user.doctors.add(doctor)

            response_data = user_data(user)
            return Response(response_data)

        if not uuid:
            return Response(
                {"error": "A uuid is required for non-guest players."},
                status=400,
            )

        user = User.objects.filter(token=token).order_by("id").first()
        created = user is None

        if created:
            user = User.objects.create(
                token=token,
                uuid=uuid,
                birth_year=birth_year,
            )
        else:
            fields_to_update = []

            if user.uuid != uuid:
                user.uuid = uuid
                fields_to_update.append("uuid")

            if birth_year is not None and user.birth_year != birth_year:
                user.birth_year = birth_year
                fields_to_update.append("birth_year")

            if fields_to_update:
                user.save(update_fields=fields_to_update)

        if doctor:
            user.doctors.add(doctor)

        response_data = user_data(user)
        return Response(response_data)

    if request.method == 'DELETE':
        try:
            user = User.objects.get(id=id)
            user.delete()
            return Response({"message": "User deleted"})
        except User.DoesNotExist:
            return Response(
                {"error": "No user was found for this id."},
                status=404,
            )

@api_view(['GET', 'POST', 'DELETE'])
def doctor_api(request, id=None):
    if request.method == "GET":
        access_response = require_game_access(request)
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
                return Response(doctor_data(obj))
            except Doctor.DoesNotExist:
                return Response(
                    {"error": "No doctor was found for this id."},
                    status=404,
                )

        token_filter = request.query_params.get("token")
        if token_filter:
            obj = Doctor.objects.filter(token=token_filter).first()
            if not obj:
                return Response(
                    {"error": "No doctor was found for this token."},
                    status=404,
                )
            return Response(doctor_data(obj))

        if not is_admin_request(request):
            return Response(
                {
                    "error": (
                        "Use a token filter when looking up doctors "
                        "from the game client."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        return Response([doctor_data(obj) for obj in Doctor.objects.all()])

    if request.method == 'POST':
        required_fields = ("last_name", "first_name", "token", "email")
        missing_fields = [
            field for field in required_fields if not request.data.get(field)
        ]

        if missing_fields:
            return Response(
                {field: ["This field is required."] for field in missing_fields},
                status=400,
            )

        try:
            obj = Doctor.objects.create(
                last_name=request.data.get("last_name"),
                first_name=request.data.get("first_name"),
                token=request.data.get("token"),
                email=request.data.get("email"),
            )
        except IntegrityError:
            return Response(
                {"error": "A doctor already exists with this token or email."},
                status=400,
            )
        return Response(doctor_data(obj))

    if request.method == 'DELETE':
        try:
            obj = Doctor.objects.get(id=id)
            obj.delete()
            return Response({"message": "Doctor deleted"})
        except Doctor.DoesNotExist:
            return Response(
                {"error": "No doctor was found for this id."},
                status=404,
            )


@api_view(['GET', 'POST', 'DELETE'])
def seed_api(request, id=None):
    if request.method == "POST":
        token_response = require_game_access(request)
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
                return Response(seed_level_data(obj))
            except SeedLevel.DoesNotExist:
                return Response(
                    {"error": "No seed level was found for this id."},
                    status=404,
                )
        return Response([seed_level_data(obj) for obj in SeedLevel.objects.all()])

    if request.method == 'POST':
        if not request.data.get("name"):
            return Response({"name": ["This field is required."]}, status=400)

        existing_seed = SeedLevel.objects.filter(name=request.data.get("name")).first()
        if existing_seed:
            return Response(seed_level_data(existing_seed))

        if not request.data.get("file"):
            return Response({"file": ["No file was submitted."]}, status=400)

        obj = SeedLevel.objects.create(
            name=request.data.get("name"),
            file=request.data.get("file"),
        )
        return Response(seed_level_data(obj))

    if request.method == 'DELETE':
        try:
            obj = SeedLevel.objects.get(id=id)
            obj.delete()
            return Response({"message": "Seed deleted"})
        except SeedLevel.DoesNotExist:
            return Response(
                {"error": "No seed level was found for this id."},
                status=404,
            )


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
                return Response(full_report_data(obj))
            except FullReport.DoesNotExist:
                return Response(
                    {"error": "No full report was found for this id."},
                    status=404,
                )
        return Response([full_report_data(obj) for obj in FullReport.objects.all()])

    if request.method == 'POST':
        token_response = require_game_access(request)
        if token_response:
            return token_response

        if not request.data.get("user"):
            return Response({"user": ["This field is required."]}, status=400)

        if not request.data.get("session_id"):
            return Response({"session_id": ["This field is required."]}, status=400)

        if not request.data.get("file"):
            return Response({"file": ["No file was submitted."]}, status=400)

        try:
            user = User.objects.get(id=int(request.data.get("user")))
        except (TypeError, ValueError, User.DoesNotExist):
            return Response(
                {"error": "No user was found for this id."},
                status=404,
            )

        seed_levels, seed_error = request_seed_levels(request)
        if seed_error == "invalid":
            return Response(
                {"error": "seed_levels must contain seed level ids."},
                status=400,
            )

        if seed_error == "missing":
            return Response(
                {"error": "No seed level was found for one of these ids."},
                status=404,
            )

        uploaded_file = request.data.get("file")
        uploaded_blocks, upload_error = uploaded_dat_blocks(uploaded_file)
        if upload_error == "invalid":
            return Response(
                {"file": ["The uploaded file must be a valid line-by-line .dat report."]},
                status=400,
            )

        app_version_code = request.data.get("app_version_code")
        if app_version_code in (None, ""):
            app_version_code = None
        else:
            try:
                app_version_code = int(app_version_code)
            except (TypeError, ValueError):
                return Response(
                    {"app_version_code": ["A valid integer is required."]},
                    status=400,
                )

        with transaction.atomic():
            obj = (
                FullReport.objects.select_for_update()
                .filter(user=user, session_id=request.data.get("session_id"))
                .first()
            )

            if not obj:
                obj = FullReport(
                    user=user,
                    session_id=request.data.get("session_id"),
                )

            current_blocks, current_error = existing_dat_blocks(obj)
            if current_error == "invalid":
                return Response(
                    {"file": ["The existing report file is not a valid .dat report."]},
                    status=400,
                )

            obj.app_version = request.data.get("app_version", "")
            obj.app_version_code = app_version_code
            obj.level_generation_version = request.data.get(
                "level_generation_version",
                "",
            )
            obj.client_platform = request.data.get("client_platform", "")

            if not obj.pk:
                obj.save()

            try:
                append_report_dat(obj, len(current_blocks), uploaded_blocks)
            except ValueError as exc:
                return Response({"file": [str(exc)]}, status=400)

            obj.save()
            obj.seed_levels.add(*seed_levels)

        return Response(full_report_data(obj))

    if request.method == 'DELETE':
        try:
            obj = FullReport.objects.get(id=id)
            obj.delete()
            return Response({"message": "Full report deleted"})
        except FullReport.DoesNotExist:
            return Response(
                {"error": "No full report was found for this id."},
                status=404,
            )


@api_view(["GET"])
def full_report_chart_api(request, id):
    admin_response = require_admin_access(request)
    if admin_response:
        return admin_response

    try:
        obj = FullReport.objects.get(id=id)
    except FullReport.DoesNotExist:
        return Response(
            {"error": "No full report was found for this id."},
            status=404,
        )

    return full_report_chart_response(obj)


def full_report_chart_response(obj):
    if not obj.file:
        return Response(
            {"error": "This full report has no file attached."},
            status=404,
        )

    try:
        with obj.file.open("r") as file_handle:
            chart = generate_full_report_chart(file_handle)
    except FileNotFoundError:
        return Response(
            {"error": "The full report file could not be found."},
            status=404,
        )
    except (UnicodeDecodeError, ReportChartError) as exc:
        if isinstance(exc, ReportChartDependencyError):
            return Response(
                {"error": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            {"error": f"The full report file could not be converted to a chart: {exc}"},
            status=400,
        )

    return HttpResponse(chart.getvalue(), content_type="image/png")
