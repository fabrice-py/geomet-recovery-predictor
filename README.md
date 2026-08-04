# Prédicteur de récupération géométallurgique

Outil de prédiction du taux de récupération d'un métal à partir de la caractérisation d'un flux minéral (granulométrie, chimie, minéralogie), combinant une **approche physique** (cinétique de flottation, courbes de partage) et une **approche data-driven** (apprentissage automatique).

## Objectif

Prédire la performance métallurgique d'un minerai à partir de ses attributs, et confronter deux familles de modèles pour évaluer leur robustesse respective.

## Démarche

- **Modèle physique** : cinétique de flottation (récupération maximale Rmax, constante de vitesse k) et courbes de partage, calés sur des paramètres issus de la littérature.
- **Modèle data-driven** : régression (scikit-learn, XGBoost) entraînée sur des données de flottation industrielles publiques.
- **Évaluation de robustesse** : confrontation des deux approches et test hors distribution.

## Données

Ce projet n'utilise **aucune donnée propriétaire ou confidentielle**. Il repose sur :
- des flux synthétiques générés à partir de paramètres publiés,
- un jeu de données public de procédé de flottation.

## Statut

Projet en cours de développement.

## Stack

Python · NumPy · pandas · SciPy · scikit-learn · XGBoost · Matplotlib

## Auteur

Fabrice TSAMO — Ingénieur des mines & géométallurgie
