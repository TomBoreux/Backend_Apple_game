from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import User, Medecin, SeedLevel, RapportMedecin, RapportComplet
from .serializers import (
    UserSerializer,
    MedecinSerializer,
    SeedLevelSerializer,
    RapportMedecinSerializer,
    RapportCompletSerializer,
)


def get_client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    real_ip = request.META.get("HTTP_X_REAL_IP")
    if real_ip:
        return real_ip.strip()

    return request.META.get("REMOTE_ADDR")


@api_view(['GET', 'POST', 'DELETE'])
def user_api(request, id=None):

    if request.method == 'GET':
        if id:
            try:
                user = User.objects.get(id=id)
                return Response(UserSerializer(user).data)
            except User.DoesNotExist:
                return Response({"error": "User not found"}, status=404)

        users = User.objects.all()
        return Response(UserSerializer(users, many=True).data)

    if request.method == 'POST':
        token = request.data.get("token")
        uuid = request.data.get("uuid")

        if not token:
            return Response({"error": "token required"}, status=400)

        if token == "guest":
            try:
                user = User.objects.get(token="guest")
            except User.DoesNotExist:
                user = User.objects.create(token="guest", uuid=None)

            # update IP
            user.device_public_ip = get_client_ip(request)
            user.save()

            return Response(UserSerializer(user).data)

        if not uuid:
            return Response({"error": "uuid required"}, status=400)

        user, created = User.objects.get_or_create(
            token=token,
            defaults={
                "uuid": uuid,
                "device_public_ip": get_client_ip(request)
            }
        )

        if not created:
            user.device_public_ip = get_client_ip(request)
            user.save()

        return Response(UserSerializer(user).data)

    if request.method == 'DELETE':
        try:
            user = User.objects.get(id=id)
            user.delete()
            return Response({"message": "User deleted"})
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=404)

@api_view(['GET', 'POST', 'DELETE'])
def medecin_api(request, id=None):

    if request.method == 'GET':
        if id:
            try:
                obj = Medecin.objects.get(id=id)
                return Response(MedecinSerializer(obj).data)
            except Medecin.DoesNotExist:
                return Response({"error": "Medecin not found"}, status=404)
        return Response(MedecinSerializer(Medecin.objects.all(), many=True).data)

    if request.method == 'POST':
        serializer = MedecinSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors)

    if request.method == 'DELETE':
        try:
            obj = Medecin.objects.get(id=id)
            obj.delete()
            return Response({"message": "Medecin deleted"})
        except Medecin.DoesNotExist:
            return Response({"error": "Medecin not found"}, status=404)


@api_view(['GET', 'POST', 'DELETE'])
def seed_api(request, id=None):

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
def rapport_medecin_api(request, id=None):

    if request.method == 'GET':
        if id:
            try:
                obj = RapportMedecin.objects.get(id=id)
                return Response(RapportMedecinSerializer(obj).data)
            except RapportMedecin.DoesNotExist:
                return Response({"error": "Rapport not found"}, status=404)
        return Response(RapportMedecinSerializer(RapportMedecin.objects.all(), many=True).data)

    if request.method == 'POST':
        serializer = RapportMedecinSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors)

    if request.method == 'DELETE':
        try:
            obj = RapportMedecin.objects.get(id=id)
            obj.delete()
            return Response({"message": "Rapport deleted"})
        except RapportMedecin.DoesNotExist:
            return Response({"error": "Rapport not found"}, status=404)

@api_view(['GET', 'POST', 'DELETE'])
def rapport_complet_api(request, id=None):

    if request.method == 'GET':
        if id:
            try:
                obj = RapportComplet.objects.get(id=id)
                return Response(RapportCompletSerializer(obj).data)
            except RapportComplet.DoesNotExist:
                return Response({"error": "Rapport complet not found"}, status=404)
        return Response(RapportCompletSerializer(RapportComplet.objects.all(), many=True).data)

    if request.method == 'POST':
        serializer = RapportCompletSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors)

    if request.method == 'DELETE':
        try:
            obj = RapportComplet.objects.get(id=id)
            obj.delete()
            return Response({"message": "Rapport complet deleted"})
        except RapportComplet.DoesNotExist:
            return Response({"error": "Rapport complet not found"}, status=404)
