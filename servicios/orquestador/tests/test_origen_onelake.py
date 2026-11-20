"""OrigenOneLake con un cliente de OneLake falso, en memoria: sin Azure."""

import hashlib
from dataclasses import dataclass

import pytest
from azure.core.exceptions import (
    ClientAuthenticationError,
    HttpResponseError,
    ResourceNotFoundError,
    ServiceRequestError,
)

from orquestador.cola import ColaEnMemoria
from orquestador.errores import ErrorDeConfiguracion, ErrorTransitorio, procesar_uno
from orquestador.origen import ArchivoDistinto, ErrorOrigen, Esperado, OrigenLocal
from orquestador.origen_onelake import ErrorDeAcceso, OrigenOneLake
from orquestador.reloj import RelojManual

FILES = "lkh.Lakehouse/Files"


@dataclass
class _Ruta:
    name: str
    is_directory: bool


class _Respuesta:
    def __init__(self, headers):
        self.headers = headers


def _http(codigo, headers=None, clase=HttpResponseError):
    error = clase(message=f"HTTP {codigo}")
    error.status_code = codigo
    error.response = _Respuesta(headers or {})
    return error


class _Descarga:
    def __init__(self, datos, corte):
        self._datos = datos
        self.size = len(datos)
        self._corte = corte

    def readinto(self, salida):
        datos = self._datos[: self._corte] if self._corte is not None else self._datos
        salida.write(datos)
        return len(datos)


class ClienteFalso:
    """Imita lo que usa OrigenOneLake de un `FileSystemClient`: `get_paths` y
    `get_file_client(...).download_file(...)`."""

    def __init__(self, archivos):
        self.archivos = {f"{FILES}/{ruta}": datos for ruta, datos in archivos.items()}
        self.fallas = {}
        """ruta completa o 'listar' → excepción que se lanza."""
        self.cortes = {}
        """ruta completa → bytes que se entregan antes de cortar."""
        self.concurrencia = None

    def get_paths(self, path, recursive=True):
        if "listar" in self.fallas:
            raise self.fallas["listar"]
        prefijo = path + "/"
        archivos = [n for n in self.archivos if n.startswith(prefijo)]
        if not archivos and path not in {n.rsplit("/", 1)[0] for n in self.archivos}:
            raise ResourceNotFoundError("no existe")
        carpetas = sorted({n.rsplit("/", 1)[0] for n in archivos} - {path})
        return [_Ruta(c, True) for c in carpetas] + [_Ruta(n, False) for n in archivos]

    def get_file_client(self, ruta):
        cliente = self

        class _Archivo:
            def download_file(self, max_concurrency=1):
                cliente.concurrencia = max_concurrency
                if ruta in cliente.fallas:
                    raise cliente.fallas[ruta]
                if ruta not in cliente.archivos:
                    raise ResourceNotFoundError("no existe")
                return _Descarga(cliente.archivos[ruta], cliente.cortes.get(ruta))

        return _Archivo()


@pytest.fixture
def cliente():
    return ClienteFalso({
        "informacion-adjuntos/fase2/Doc1/Documentos del proceso/cpc.pdf": b"cpc",
        "informacion-adjuntos/fase2/Doc1/Oferentes/A/sub/carta.pdf": b"carta",
        "informacion-adjuntos/fase2/Doc2/x.pdf": b"x",
    })


@pytest.fixture
def origen(cliente):
    return OrigenOneLake("ws", "lkh", cliente=cliente, concurrencia_por_archivo=3)


def test_lista_archivos_relativos_y_ordenados(origen):
    assert origen.listar("informacion-adjuntos/fase2/Doc1") == [
        "Documentos del proceso/cpc.pdf", "Oferentes/A/sub/carta.pdf"]


def test_acepta_el_lakehouse_con_sufijo(cliente):
    origen = OrigenOneLake("ws", "lkh.Lakehouse", cliente=cliente)
    assert origen.listar("informacion-adjuntos/fase2/Doc2") == ["x.pdf"]


def test_baja_con_varias_partes_a_la_vez(origen, cliente, tmp_path):
    destino = tmp_path / "t/carta.pdf"
    origen.bajar("informacion-adjuntos/fase2/Doc1/Oferentes/A/sub/carta.pdf", destino)
    assert destino.read_bytes() == b"carta"
    assert cliente.concurrencia == 3


def test_revisa_tamano_y_md5(origen, tmp_path):
    ruta = "informacion-adjuntos/fase2/Doc2/x.pdf"
    md5 = hashlib.md5(b"x").hexdigest()
    origen.bajar(ruta, tmp_path / "a.pdf", Esperado(tamano=1, md5=md5.upper()))
    assert (tmp_path / "a.pdf").read_bytes() == b"x"
    with pytest.raises(ArchivoDistinto):
        origen.bajar(ruta, tmp_path / "b.pdf", Esperado(tamano=2))
    with pytest.raises(ArchivoDistinto):
        origen.bajar(ruta, tmp_path / "c.pdf", Esperado(md5=hashlib.md5(b"y").hexdigest()))
    assert not (tmp_path / "b.pdf").exists() and not (tmp_path / "c.pdf").exists()


def test_descarga_cortada_no_deja_archivo(origen, cliente, tmp_path):
    ruta = "informacion-adjuntos/fase2/Doc1/Oferentes/A/sub/carta.pdf"
    cliente.cortes[f"{FILES}/{ruta}"] = 2
    with pytest.raises(ArchivoDistinto):
        origen.bajar(ruta, tmp_path / "carta.pdf")
    assert not (tmp_path / "carta.pdf").exists()


@pytest.mark.parametrize("ruta", ["../fuera", "/Files", "a/../../b", ""])
def test_no_sale_de_files(origen, ruta, tmp_path):
    with pytest.raises(ErrorOrigen):
        origen.listar(ruta)
    with pytest.raises(ErrorOrigen):
        origen.bajar(ruta, tmp_path / "x")


def test_lo_que_no_existe_es_error_de_origen(origen, tmp_path):
    with pytest.raises(ErrorOrigen):
        origen.listar("informacion-adjuntos/fase2/Doc9")
    with pytest.raises(ErrorOrigen):
        origen.bajar("informacion-adjuntos/fase2/Doc1/no.pdf", tmp_path / "no.pdf")
    assert not (tmp_path / "no.pdf").exists()


def test_un_listado_fuera_de_la_carpeta_es_error(origen, cliente):
    cliente.get_paths = lambda path, recursive=True: [_Ruta(f"{FILES}/otra/a.pdf", False)]
    with pytest.raises(ErrorOrigen):
        origen.listar("informacion-adjuntos")


@pytest.mark.parametrize("falla", [
    _http(401), _http(403), ClientAuthenticationError("sin identidad"),
])
def test_sin_permiso_es_error_de_acceso(origen, cliente, falla):
    cliente.fallas["listar"] = falla
    with pytest.raises(ErrorDeAcceso) as error:
        origen.listar("informacion-adjuntos")
    assert "informacion" not in str(error.value)
    assert isinstance(error.value, ErrorDeConfiguracion)


def test_el_error_de_acceso_trae_los_codigos_y_no_el_texto(origen, cliente):
    falla = _http(403)
    falla.error_code = "AuthorizationPermissionMismatch"
    cliente.fallas["listar"] = falla
    with pytest.raises(ErrorDeAcceso) as error:
        origen.listar("informacion-adjuntos")
    assert str(error.value).endswith("HTTP 403 [AuthorizationPermissionMismatch]")

    cliente.fallas["listar"] = ClientAuthenticationError(
        "AzureCliCredential: ERROR: AADSTS50078: MFA vencida para usuario@empresa.com")
    with pytest.raises(ErrorDeAcceso) as error:
        origen.listar("informacion-adjuntos")
    assert "[AADSTS50078]" in str(error.value)
    assert "usuario" not in str(error.value)


@pytest.mark.parametrize("falla, espera", [
    (_http(429, {"Retry-After": "7"}), 7.0),
    (_http(503), None),
    (_http(500, {"Retry-After": "no es un número"}), None),
    (ServiceRequestError("sin conexión"), None),
])
def test_fallas_transitorias(origen, cliente, falla, espera, tmp_path):
    ruta = "informacion-adjuntos/fase2/Doc2/x.pdf"
    cliente.fallas[f"{FILES}/{ruta}"] = falla
    with pytest.raises(ErrorTransitorio) as error:
        origen.bajar(ruta, tmp_path / "x.pdf")
    assert error.value.espera_s == espera
    assert not (tmp_path / "x.pdf").exists()


def test_otra_respuesta_no_se_disfraza(origen, cliente):
    cliente.fallas["listar"] = _http(400)
    with pytest.raises(HttpResponseError):
        origen.listar("informacion-adjuntos")


def test_el_bucle_no_reintenta_un_error_de_acceso():
    cola = ColaEnMemoria(RelojManual())

    class Manejador:
        cola = "normalizar"
        fallas = []

        def procesar(self, cuerpo):
            raise ErrorDeAcceso("OneLake no dejó bajar: HTTP 403")

        def al_fallar(self, cuerpo, motivo):
            self.fallas.append(motivo)

    cola.publicar("normalizar", {"id_proceso": "Doc1"})
    manejador = Manejador()
    resultado = procesar_uno(cola, manejador)
    assert resultado.desenlace == "a_errores"
    assert resultado.motivo == "Configuración: OneLake no dejó bajar: HTTP 403"
    assert len(manejador.fallas) == 1
    assert cola.recibir("normalizar") is None


def test_origen_local_tambien_revisa_lo_esperado(tmp_path):
    (tmp_path / "o").mkdir()
    (tmp_path / "o/a.pdf").write_bytes(b"abc")
    origen = OrigenLocal(tmp_path / "o")
    origen.bajar("a.pdf", tmp_path / "d/a.pdf", Esperado(tamano=3, md5=hashlib.md5(b"abc").hexdigest()))
    with pytest.raises(ArchivoDistinto):
        origen.bajar("a.pdf", tmp_path / "d/b.pdf", Esperado(tamano=4))
    assert not (tmp_path / "d/b.pdf").exists()
