"""Alias de `mensajeria.cola`, que vive en `servicios/mensajeria` (T01 de `tasks-workers.md`).

Se reemplaza este módulo por el de la mensajería, así los imports del orquestador
y los `monkeypatch` de las pruebas siguen apuntando al mismo objeto.
"""

import sys

from mensajeria import cola as _modulo

sys.modules[__name__] = _modulo
