"""Configuration pytest : ajoute src/ au chemin d'import, car nos modules y vivent : ainsi
les tests peuvent importer feed_generator, separation, flowsheet, etc. directement."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))