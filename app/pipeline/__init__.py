"""Pipeline genómico de SIRFA: validación, calidad, especie, locus K, genes e ingesta del banco.

Orden en que el worker aplica los pasos a un genoma (ver `trabajos.py`):
FASTA válido -> calidad (`qc`) -> especie (`especie`) -> locus K (`locus_k`) -> genes (`genes`).
El primer paso que rechaza el genoma detiene el resto.
"""
