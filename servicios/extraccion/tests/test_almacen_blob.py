"""De una entrega del orquestador a la extracción, con Blob Storage en memoria."""

import json
import logging
from unittest.mock import Mock

import pytest
from azure.core.exceptions import ClientAuthenticationError, ServiceRequestError
from normalizacion import almacen_blob
from orquestador.clasificador import ClasificadorFalso
from orquestador.local import Corrida, aviso, conteos, guardar_salida
from orquestador.origen import OrigenLocal

from conftest import AQUI, FICHA_V21
from extraccion import cli
from extraccion.entrada import ErrorDeSolicitud, preparar, ubicar
from extraccion.resultados import Clave, ResultadosEnCarpeta
from fabrica import PROCESO, pdf

CUENTA = "cuentafalsa"
CONTENEDOR = "evaluacion-ofertas"
RAIZ_BLOB = f"https://{CUENTA}.blob.core.windows.net/{CONTENEDOR}/"


@pytest.fixture
def corrida_blob(tmp_path, contenedor_blob_falso):
    origen = tmp_path / "datalake"
    ruta_proceso = f"procesos/{PROCESO}"
    documento = origen / ruta_proceso / "OF-001" / "certificado.pdf"
    documento.parent.mkdir(parents=True)
    documento.write_bytes(pdf(1, "Certificado inventado"))
    clasificacion = tmp_path / "clasificacion.csv"
    clasificacion.write_text(
        "id_oferente,ruta_origen,pagina_inicio,pagina_fin,tipo_documental,confianza,subtipo\n"
        "OF-001,certificado.pdf,,,TD-16,0.97,\n", encoding="utf-8",
    )
    with almacen_blob.AlmacenBlob(CUENTA, CONTENEDOR, cliente=contenedor_blob_falso) as almacen:
        corrida = Corrida(OrigenLocal(origen), almacen, ClasificadorFalso(clasificacion))
        corrida.publicar_aviso(aviso(PROCESO, ruta_proceso, corrida.reloj))
        corrida.correr()

    resumen = conteos(corrida, PROCESO)
    assert resumen["mensajes_en_errores"] == {}
    salida = tmp_path / "corrida"
    salida.mkdir()
    guardar_salida(corrida, salida, resumen)
    jsonl = salida / "solicitudes-extraccion.jsonl"
    [solicitud] = [json.loads(linea) for linea in jsonl.read_text(encoding="utf-8").splitlines()]
    return salida, jsonl, solicitud


def test_lee_en_blob_el_pdf_y_la_lectura_exportados_por_el_orquestador(corrida_blob, contenedor_blob_falso):
    salida, _, solicitud = corrida_blob
    lectura, pdf_normalizado = solicitud["lectura"], solicitud["archivo"]["uri"]
    assert lectura.startswith(RAIZ_BLOB) and pdf_normalizado.startswith(RAIZ_BLOB)
    blobs = contenedor_blob_falso.blobs
    manifiesto = json.loads(blobs[f"{PROCESO}/OF-001/manifiesto.json"])
    [archivo] = manifiesto["archivos"]
    assert (archivo["lectura"], archivo["pdf"]) == (lectura, pdf_normalizado)
    assert {ruta.name for ruta in salida.iterdir()} == {
        "estado.json", "solicitudes-extraccion.jsonl", "errores.json", "conteos.json",
    }

    with almacen_blob.AlmacenBlob(CUENTA, CONTENEDOR, cliente=contenedor_blob_falso) as almacen:
        entrada = preparar(solicitud, almacen)

    assert entrada.lectura == json.loads(blobs[lectura.removeprefix(RAIZ_BLOB)])
    assert "Certificado inventado" in entrada.paginas()[0]["texto"]
    assert entrada.pdf == blobs[pdf_normalizado.removeprefix(RAIZ_BLOB)]
    assert entrada.pdf.startswith(b"%PDF-")


def test_una_solicitud_con_uri_de_blob_y_local_no_reubica_la_uri_local(corrida_blob, contenedor_blob_falso):
    salida, _, solicitud = corrida_blob
    ruta_blob = solicitud["archivo"]["uri"].removeprefix(RAIZ_BLOB)
    assert ruta_blob in contenedor_blob_falso.blobs
    uri_local = (salida / "almacen" / ruta_blob).as_uri()
    solicitud["archivo"]["uri"] = uri_local

    with almacen_blob.AlmacenBlob(CUENTA, CONTENEDOR, cliente=contenedor_blob_falso) as almacen:
        assert ubicar(almacen, uri_local) == uri_local
        with pytest.raises(ErrorDeSolicitud) as error:
            preparar(solicitud, almacen)

    assert error.value.estado == "error_proceso"
    assert error.value.como_error() == {
        "codigo": "URI_INVALIDA",
        "mensaje": "No se puede leer el PDF normalizado: su URI no es del almacén que se usa.",
        "reintentable": False,
    }


@pytest.mark.parametrize("falla, codigo, reintentable", [
    (ServiceRequestError, "ALMACEN_NO_DISPONIBLE", True),
    (ClientAuthenticationError, "ALMACEN_SIN_PERMISO", False),
])
def test_las_fallas_de_blob_son_errores_de_proceso_sin_datos_privados(
    corrida_blob, contenedor_blob_falso, falla, codigo, reintentable,
):
    _, _, solicitud = corrida_blob
    contenedor_blob_falso.fallas["download_blob"] = falla(f"secreto-inventado {solicitud['lectura']}")

    with almacen_blob.AlmacenBlob(CUENTA, CONTENEDOR, cliente=contenedor_blob_falso) as almacen:
        with pytest.raises(ErrorDeSolicitud) as error:
            preparar(solicitud, almacen)

    assert error.value.estado == "error_proceso"
    assert error.value.como_error() == {"codigo": codigo, "mensaje": "Blob leer", "reintentable": reintentable}


def test_extraer_usa_blob_sin_almacen_local_y_cierra_el_almacen(
    corrida_blob, contenedor_blob_falso, monkeypatch, capsys, caplog,
):
    salida, jsonl, solicitud = corrida_blob
    almacen = almacen_blob.AlmacenBlob(CUENTA, CONTENEDOR, cliente=contenedor_blob_falso)
    cerrar = Mock(wraps=almacen.cerrar)
    monkeypatch.setattr(almacen, "cerrar", cerrar)
    fabrica = Mock(return_value=almacen)
    monkeypatch.setattr(almacen_blob, "almacen_blob_desde_entorno", fabrica)
    monkeypatch.setenv("ALMACEN_BLOB_CUENTA", CUENTA)

    def avisar_al_descargar(etapa):
        if etapa == "download_blob":
            logging.getLogger("azure.identity").warning("secreto-inventado")

    monkeypatch.setattr(contenedor_blob_falso, "_fallar", avisar_al_descargar)
    argumentos = [str(jsonl), "--corrida", str(salida), "--modelo", f"archivo:{FICHA_V21}",
                  "--respuestas", str(AQUI / "respuestas")]
    with caplog.at_level(logging.DEBUG):
        assert cli.main(argumentos) == 0

    fabrica.assert_called_once_with()
    cerrar.assert_called_once_with()
    impreso = capsys.readouterr()
    assert impreso.err.splitlines() == ["Los documentos se leen de Blob Storage."]
    assert CUENTA not in impreso.out + impreso.err
    assert "secreto-inventado" not in caplog.text + impreso.out + impreso.err
    assert json.loads(impreso.out)["por_estado"] == {"ok": 1}
    assert not (salida / "almacen").exists()
    assert (salida / "extraccion" / "fichas" / "v21" / "TD-16.json").is_file()
    assert ResultadosEnCarpeta(salida / "extraccion").buscar(Clave.de(solicitud))["estado"] == "ok"


@pytest.mark.parametrize("cuenta", ["", "CuentaFalsa!"])
def test_extraer_rechaza_una_cuenta_blob_invalida(tmp_path, capsys, monkeypatch, cuenta):
    monkeypatch.setenv("ALMACEN_BLOB_CUENTA", cuenta)
    jsonl = tmp_path / "solicitudes-extraccion.jsonl"
    jsonl.write_text("", encoding="utf-8")

    assert cli.main([str(jsonl), "--corrida", str(tmp_path), "--modelo", f"archivo:{FICHA_V21}"]) == 2

    impreso = capsys.readouterr()
    assert impreso.out == ""
    assert impreso.err.splitlines() == ["ALMACEN_BLOB_CUENTA falta o es inválida."]
