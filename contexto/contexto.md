Nueva iniciativa que pretende desarrollar un agente de Microsoft foundry para que haga parte de un proceso de clasificacion y extraccion de informacion documental en procesos de contratacion de provedores. Procesos similares se han llevado a cabo con anterioridad usando Document Intelligence y herramientas similares, pero tomamos la decision de hacerlo de manera agentica puesto que el avanza de los modelos de inteligencia artificial nos puede ayudar a hacer el proceso mas facil de desarrollar.

Va a haber un trigger que lanzara el proceso por uno o dos agentes (aun no se decide si uno para clasificar y otro para extraer o que el mismo haga ambas cosas).
Hay un listado de 39 documentos en este momento, desde cartas, documentos de identidad, RUT(Colombia), formatos bancaria o de otras entidades publicas.
La idea es construir una especia de modelo semantico/operativo u ontologias que sirva de contexto para el agente, donde se identifique cada documentos, que informacion trae, como identificarlo, pero sin entrenamiento de imagenes, solo texto. (Aun asi el documento puede ser un pdf de imagenes por ejemplo, o un archivo .jpg.
Este modelo u ontologia estaria almacenado en BD y seria extraido en runtime por el agente para identificar que documento puede ser el que esta revisando. Es demasiada informacion para un prompt.
Se prefiere no usar una base de conociento vectorial.
Debe aceptar la mayoria de tipos de archivos posibles entre pdf, excel, docx, imagenes.
Se realizan aproximadamente 400 ofertas a provedores a las cuales llegan hasta 10 ofertantes con unos 12 documentos cada uno. Todo eso en un año.
Quiero que nos enfoquemos en la parte tecnica. Realizar una serie de pruebas tecnicas con las herramientas de foundry.
