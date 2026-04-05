from rest_framework import serializers
from .models import User, Medecin, SeedLevel, RapportMedecin, RapportComplet

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = '__all__'

class MedecinSerializer(serializers.ModelSerializer):
    class Meta:
        model = Medecin
        fields = '__all__'

class SeedLevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = SeedLevel
        fields = '__all__'

class RapportMedecinSerializer(serializers.ModelSerializer):
    class Meta:
        model = RapportMedecin
        fields = '__all__'

class RapportCompletSerializer(serializers.ModelSerializer):
    class Meta:
        model = RapportComplet
        fields = '__all__'