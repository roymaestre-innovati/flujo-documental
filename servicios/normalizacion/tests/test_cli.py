import os

import pytest

from normalizacion import VERSION
from normalizacion.cli import main
from normalizacion.inventario import recorrer


@pytest.fixture
def entrega(tmp_path):
    carpeta = tmp_path / "entrega"
    for ruta in ("b.pdf", "a/carta.docx", "a/sub/foto.jpg", "__MACOSX/._b.pdf", ".DS_Store"):
        archivo = carpeta / ruta
        archivo.parent.mkdir(parents=True, exist_ok=True)
        archivo.write_bytes(ruta.encode("utf-8"))
    (carpeta / "vacia").mkdir()
    return carpeta


def test_recorre_carpetas_anidadas_en_orden(entrega):
    assert recorrer(entrega) == [
        ".DS_Store",
        "__MACOSX/._b.pdf",
        "a/carta.docx",
        "a/sub/foto.jpg",
        "b.pdf",
    ]


def test_no_sigue_enlaces_simbolicos(entrega, tmp_path):
    fuera = tmp_path / "fuera"
    fuera.mkdir()
    (fuera / "secreto.pdf").write_bytes(b"x")
    os.symlink(fuera, entrega / "enlace")
    os.symlink(fuera / "secreto.pdf", entrega / "enlace.pdf")
    assert not any("secreto" in r or r.startswith("enlace") for r in recorrer(entrega))


def test_recorrer_exige_carpeta(tmp_path):
    with pytest.raises(NotADirectoryError):
        recorrer(tmp_path / "no-existe")


def test_comando_cuenta_sin_mostrar_nombres(entrega, tmp_path, capsys):
    codigo = main([str(entrega), "--proceso", "SR0000000001", "--oferente", "OF-002", "--salida", str(tmp_path / "salida")])
    salida = capsys.readouterr().out
    assert codigo == 0
    assert "SR0000000001/OF-002: 3 archivos, 0 duplicados, 2 descartados." in salida
    assert "carta.docx" not in salida and "foto.jpg" not in salida


def test_comando_entrega_del_proceso(entrega, tmp_path, capsys):
    assert main([str(entrega), "--proceso", "SR0000000001", "--salida", str(tmp_path / "salida")]) == 0
    assert "SR0000000001/PROCESO" in capsys.readouterr().out


def test_comando_carpeta_inexistente(tmp_path):
    with pytest.raises(SystemExit) as salida:
        main([str(tmp_path / "no"), "--proceso", "SR0000000001", "--salida", str(tmp_path)])
    assert salida.value.code == 2


def test_comando_exige_proceso_y_salida(entrega):
    with pytest.raises(SystemExit) as salida:
        main([str(entrega)])
    assert salida.value.code == 2


def test_comando_version(capsys):
    with pytest.raises(SystemExit):
        main(["--version"])
    assert VERSION in capsys.readouterr().out
