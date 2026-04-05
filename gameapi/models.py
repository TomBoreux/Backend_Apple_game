from django.db import models


# MEDECIN
class Medecin(models.Model):
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100)
    token = models.CharField(max_length=255, unique=True)
    email = models.EmailField(max_length=100, unique=True)

    def __str__(self):
        return f"{self.nom} {self.prenom}"


# USER
class User(models.Model):
    token = models.CharField(max_length=255, unique=True)
    pseudo = models.CharField(max_length=100, unique=True, default="guest")
    medecins = models.ManyToManyField(Medecin, related_name="users")  # SOIGNER

    def __str__(self):
        return f"{self.token} {self.pseudo}"


# SEED LEVEL
class SeedLevel(models.Model):
    nom = models.CharField(max_length=100)
    seed_file = models.FileField(upload_to="seeds/")

    def __str__(self):
        return self.nom


# RAPPORT MEDECIN
class RapportMedecin(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="rapports")
    seed = models.ForeignKey(SeedLevel, on_delete=models.CASCADE)
    fichier = models.FileField(upload_to="rapports/medecin/")
    date = models.DateTimeField(auto_now_add=True)

    medecins = models.ManyToManyField(Medecin, related_name="rapports_consultes")  # CONSULTE

    def __str__(self):
        return f"Rapport {self.id} - User {self.user.id}"


# RAPPORT COMPLET
class RapportComplet(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="rapports_complets")
    fichier = models.FileField(upload_to="rapports/complet/")
    date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"RapportComplet {self.id}"