"""El subconjunto del SDK de Blob Storage que usa el almacén, en memoria."""

from dataclasses import dataclass

from azure.core.exceptions import HttpResponseError, ResourceExistsError, ResourceNotFoundError


@dataclass
class _Respuesta:
    status_code: int
    headers: dict
    cuerpo: str
    reason: str = "Falla simulada"

    def text(self):
        return self.cuerpo


def error_http(estado, codigo=None, cabeceras=None, texto="Falla simulada", clase=HttpResponseError):
    respuesta = _Respuesta(estado, cabeceras or {}, texto)
    error = clase(message=texto, response=respuesta)
    error.error_code = codigo
    return error


@dataclass
class _Propiedades:
    name: str


class _DescargaFalsa:
    def __init__(self, contenedor, datos):
        self._contenedor = contenedor
        self._datos = datos

    def readall(self):
        self._contenedor._fallar("readall")
        return self._datos


class _BlobFalso:
    def __init__(self, contenedor, nombre):
        self._contenedor = contenedor
        self._nombre = nombre

    def _comprobar_existencia(self):
        if self._nombre not in self._contenedor.blobs:
            raise error_http(404, "BlobNotFound", clase=ResourceNotFoundError)

    def upload_blob(self, datos, *, overwrite, content_settings):
        self._contenedor._fallar("upload_blob")
        if not overwrite and self._nombre in self._contenedor.blobs:
            raise error_http(409, "BlobAlreadyExists", clase=ResourceExistsError)
        self._contenedor.blobs[self._nombre] = datos
        self._contenedor.cargas.append((self._nombre, overwrite, content_settings.content_type))

    def download_blob(self):
        self._contenedor._fallar("download_blob")
        self._comprobar_existencia()
        return _DescargaFalsa(self._contenedor, self._contenedor.blobs[self._nombre])

    def get_blob_properties(self):
        self._contenedor._fallar("get_blob_properties")
        self._comprobar_existencia()
        return _Propiedades(self._nombre)


class ContenedorFalso:
    def __init__(self, blobs=None):
        self.blobs = dict(blobs or {})
        self.fallas = {}
        """Excepciones por método del SDK o para la página siguiente del listado."""
        self.cargas = []
        self.prefijos_listados = []
        self.cierres = 0

    def _fallar(self, etapa):
        if etapa in self.fallas:
            raise self.fallas[etapa]

    def get_blob_client(self, nombre):
        return _BlobFalso(self, nombre)

    def list_blobs(self, *, name_starts_with):
        self.prefijos_listados.append(name_starts_with)
        self._fallar("list_blobs")
        return self._listar(name_starts_with)

    def _listar(self, prefijo):
        for nombre in self.blobs:
            if nombre.startswith(prefijo):
                yield _Propiedades(nombre)
                self._fallar("pagina_siguiente")

    def close(self):
        self.cierres += 1
        self._fallar("close")
