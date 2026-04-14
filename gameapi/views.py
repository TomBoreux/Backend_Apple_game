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

@api_view(['GET', 'POST', 'PUT', 'DELETE','PATCH'])
def user_api(request, id=None):

    # GET
    if request.method == 'GET':
        if id:
            try:
                user = User.objects.get(id=id)
            except User.DoesNotExist:
                return Response({"error": "User not found"}, status=404)

            serializer = UserSerializer(user)
            return Response(serializer.data)
        else:
            users = User.objects.all()
            serializer = UserSerializer(users, many=True)
            return Response(serializer.data)

    # POST (create)
    if request.method == 'POST':
        serializer = UserSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors)

    # PUT (update COMPLET)
    if request.method == 'PUT':
        try:
            user = User.objects.get(id=id)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=404)

        serializer = UserSerializer(user, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors)

    # PATCH (update PARTIEL)
    if request.method == 'PATCH':
        try:
            user = User.objects.get(id=id)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=404)

        serializer = UserSerializer(user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors)


    # DELETE
    if request.method == 'DELETE':
        try:
            user = User.objects.get(id=id)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=404)

        user.delete()
        return Response({"message": "User deleted"})

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
