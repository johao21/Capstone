"""Modelo de predicción de compatibilidad fago–hospedador (OE3): ESM-2 + XGBoost + SHAP.

- `datos`: lectura del conjunto público PhageHostLearn (Boeckaerts et al., 2024).
- `modelo`: entrenamiento, validación cruzada y predicción con explicación.
- `entrenar`: comando que entrena, guarda los artefactos en `ml/models/` y los registra en la base de datos.
"""
