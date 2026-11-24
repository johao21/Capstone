"""Validación y lectura de FASTA: casos válidos, comprimidos y los distintos tipos de archivo inválido."""
import gzip

from pipeline.fasta import leer_fasta, validar_fasta


def escribir(ruta, contenido: str):
    """Escribe `contenido` en `ruta` y devuelve la ruta."""
    ruta.write_text(contenido, encoding="utf-8")
    return ruta


def test_fasta_valido_cuenta_registros_y_longitud(tmp_path):
    f = escribir(tmp_path / "g.fasta", ">c1 descripcion\nACGTAC\nGT\n>c2\nNNACGT\n")
    r = validar_fasta(f)
    assert r.valido
    assert r.registros == 2
    assert r.longitud_total == 14
    assert r.errores == []


def test_fasta_comprimido_con_gzip(tmp_path):
    f = tmp_path / "g.fasta.gz"
    with gzip.open(f, "wt", encoding="utf-8") as fh:
        fh.write(">c1\nACGT\n")
    assert validar_fasta(f).valido


def test_archivo_vacio_se_rechaza(tmp_path):
    r = validar_fasta(escribir(tmp_path / "vacio.fasta", ""))
    assert not r.valido
    assert "no contiene registros" in r.errores[0]


def test_texto_sin_encabezado_se_rechaza(tmp_path):
    r = validar_fasta(escribir(tmp_path / "texto.fasta", "hola mundo\n"))
    assert not r.valido


def test_proteina_no_es_fasta_de_nucleotidos(tmp_path):
    r = validar_fasta(escribir(tmp_path / "prot.fasta", ">p1\nMKVLAAGIVEQ\n"))
    assert not r.valido
    assert "caracteres no válidos" in r.errores[0]
    assert len(r.errores) == 1  # no se agrega un falso "sin secuencia"


def test_registro_sin_secuencia_se_rechaza(tmp_path):
    r = validar_fasta(escribir(tmp_path / "x.fasta", ">c1\n>c2\nACGT\n"))
    assert not r.valido
    assert "no tiene secuencia" in r.errores[0]


def test_identificador_repetido_se_rechaza(tmp_path):
    r = validar_fasta(escribir(tmp_path / "x.fasta", ">c1\nACGT\n>c1\nACGT\n"))
    assert not r.valido
    assert "repetido" in r.errores[0]


def test_gzip_corrupto_informa_el_error(tmp_path):
    f = tmp_path / "malo.fasta.gz"
    f.write_bytes(b"esto no es gzip")
    r = validar_fasta(f)
    assert not r.valido
    assert "no se pudo leer" in r.errores[0]


def test_se_limita_la_cantidad_de_errores(tmp_path):
    cuerpo = ">c1\n" + "".join("XYZ\n" for _ in range(50))
    r = validar_fasta(escribir(tmp_path / "x.fasta", cuerpo), max_errores=3)
    assert len(r.errores) == 3


def test_leer_fasta_une_lineas_y_pasa_a_mayusculas(tmp_path):
    f = escribir(tmp_path / "g.fasta", ">c1 d\nacg\ntt\n>c2\nGG\n")
    assert list(leer_fasta(f)) == [("c1", "ACGTT"), ("c2", "GG")]
