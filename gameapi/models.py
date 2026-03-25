from django.db import models
from django.db import models

# USER
class User(models.Model):
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    annee_naissance = models.IntegerField()

    def __str__(self):
        return f"{self.prenom} {self.nom}"


# SEEDS LEVEL
class SeedLevel(models.Model):
    nom = models.CharField(max_length=100)
    seed_file = models.FileField(upload_to="seeds/")

    def __str__(self):
        return f"Seed {self.id}"


# RAPPORT
class Rapport(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    fichier = models.FileField(upload_to="rapports/")

    def __str__(self):
        return f"Rapport {self.id} - {self.user}"

