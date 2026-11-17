# Entrega

## Resumen

Herramienta para que la organización meta las inscripciones de cada carrera desde las plataformas online y desde la
tienda, y vea a cada corredor con su **categoría** y su **dorsal**. Hace esto:

- **Importa** los tres formatos que llegan hoy (xlsx de la Plataforma A, csv de la Plataforma B y csv de la tienda) en segundo plano, con progreso, en cola por carrera y con un informe de lo que ha pasado con cada fila.
- **Reimporta** cada noche el listado completo sin cambiar dorsales ni escribir nada si no hay cambios.
- **Detecta duplicados** dentro de un fichero y entre canales.
- La **tienda da de alta** a la gente en la herramienta, con un aviso de «ya inscrita» antes de guardar.
- **Busca** por nombre, email o dorsal.
- Gestiona el **aforo** con lista de espera.
- **Manda la confirmación** por email con un botón o a una hora programada, aunque el proveedor falle.

Lo que pide el enunciado como mínimo (meter las inscripciones y verlas con categoría y dorsal) funciona con las cuatro muestras, también con el maratón de 20.000 filas (20 s en Docker).

## Cómo probarlo

```bash
docker compose up --build
```

La aplicación está en http://localhost:5173. Además de los servicios del esqueleto, hay un servicio `beat` que late cada minuto para el envío programado. Un recorrido de unos minutos con las muestras de `samples/`:

1. En **10K Nocturna del Puerto**, **Cambiar aforo** a 20.
2. **Importar un listado**: canal Plataforma B, `plataforma_b_10k.csv`. Salen 17 altas con dorsales del 1 al 17 y 1 rechazada (línea 11, `31/02/1990`). El informe se abre en un diálogo.
3. Importar `tienda_10k.csv` con el canal Tienda. Salen 3 altas con dorsal (18–20), 9 en lista de espera y **2 ya inscritas por la Plataforma B** (Claudia Benítez y Álex Ruiz) con sus diferencias, sin un segundo dorsal.
4. **Alta en tienda** con el email de Claudia en mayúsculas: al salir del campo avisa «Ya inscrita por Plataforma B, dorsal 9» antes de guardar.
5. Buscar `garcia`: dorsales 3 y 16. Buscar `17`: el dorsal 17.
6. Dar de **baja** el dorsal 5: entra la primera de la espera (Íñigo) con el **dorsal 21**. El 5 no se reutiliza.
7. **Enviar confirmaciones pendientes**: cada fila enseña el estado de su email. Lo que llega al simulador se ve en http://localhost:9000/v1/messages.
8. En **Configuración** se cambian la hora del envío programado, la plantilla y el ritmo. Ahí también se ven los últimos envíos.
9. El maratón (`plataforma_b_maraton.csv`, Plataforma B) da 19.800 inscripciones y 80 rechazadas en 4 grupos. Si se reimporta, no hay ninguna novedad.

## Qué he construido y por qué

### Lo que vi de primeras al leer el enunciado

- **Hace falta una plataforma unificada para gestionar las carreras.** Hoy todo vive en hojas de cálculo repartidas entre dos plataformas y una tienda, y por eso nadie se entera de los duplicados hasta el día de la carrera. La herramienta tiene que ser el único sitio donde está cada inscripción, también las de la tienda.
- **Hay que normalizar los datos y estar abierto a nuevos proveedores y formatos.** Cada canal manda lo mismo a su manera: Excel con fechas de Excel, CSV en UTF-8 con `,`, CSV de Windows con `;` y cabeceras con tilde. Todo tiene que pasar por una sola normalización, y una plataforma o un formato nuevo no deberían obligar a reescribir la importación.
- **El envío de correos tiene que ser automático y programado, y robusto ante los errores documentados del proveedor.** Hay 500, respuestas lentas que sí se aceptan, 429 con `Retry-After`, y una idempotencia que hay que usar bien. Con 20.000 corredores y un límite de 20 por segundo, el envío no puede depender de una petición ni de que alguien se acuerde.
- **Hay que gestionar a los inscritos según las reglas de negocio**: edad mínima y categoría el día de la carrera, dorsal único por carrera, aforo con lista de espera y duplicados entre canales.

### Prioridades

Este fue el orden, de más a menos valor y riesgo. Las ocho están construidas.

1. **Importar los listados**, en segundo plano, con progreso y con un informe de lo que ha pasado con cada fila. Es el mínimo del enunciado y donde están los datos reales más sucios.
2. **Categoría y dorsal** correctos: la edad se calcula el día de la carrera y el dorsal es único aunque varias personas importen a la vez.
3. **Reimportación idempotente** del listado completo de cada noche, sin cambiar dorsales.
4. **Duplicados**:
   - el mismo email por otro canal no recibe un segundo dorsal y genera un aviso;
   - mismo nombre y fecha con otro email: «posible duplicado», para que decida una persona.
5. **La tienda da de alta en la herramienta** en vez de en su Excel, con un aviso de «ya inscrita» antes de guardar. Es la única forma de evitar el duplicado en origen.
6. **Búsqueda** por nombre, email o dorsal.
7. **Aforo y lista de espera** por carrera; una baja deja entrar al siguiente.
8. **Emails de confirmación** con reintentos e idempotencia, lanzados con un botón o programados, y una vista de **configuración**.

Además, con lo que salió por el camino:
- **Corregir los datos** de una inscripción.
- Marcar un posible duplicado como **«No es duplicado»**.
- Un **panel de cifras** por carrera (ocupación, categorías, canales, emails) y otro con todas las carreras.

### Qué hay

**Pantallas** (React + MUI, sin dependencias nuevas):
- **Carreras**: panel con todas las carreras y su ocupación.
- **Detalle de carrera**:
  - panel de cifras;
  - importar con progreso y cola;
  - informe en un diálogo, agrupado por tipo de incidencia;
  - tabla paginada con búsqueda y estado;
  - marcas de duplicado y de ausencia en la tabla;
  - alta en tienda;
  - corregir datos y dar de baja;
  - envío de confirmaciones con el estado del email en cada fila.
- **Configuración**: envío programado (sí o no, y la hora), plantilla del email, ritmo, intentos, minutos para dar por caída una importación, y los últimos envíos.

Los avisos salen en un *toast*. Los errores no se cierran solos.

**Backend** (`backend/races/`, en capas):
- `domain/`: código puro, sin base de datos:
  - el normalizador común;
  - las reglas (edad, categoría, tallas);
  - la clave de duplicado y las diferencias;
  - la plantilla del email.
- `infrastructure/`: los lectores de xlsx y csv, con mapeo de columnas por canal, y los proveedores de email detrás de una interfaz.
- `application/`: los casos de uso:
  - inscribir, dar de baja y cambiar el aforo, con la carrera bloqueada;
  - importar;
  - enviar confirmaciones;
  - el latido programado.
- `api/`: las vistas validan y delegan en `application/`.

**API** (DRF):
- carreras, con sus cuentas, el aforo y las cifras;
- importaciones e informe;
- inscripciones: lista, búsqueda, comprobación antes del alta, alta, corrección, baja y «no es duplicado»;
- confirmaciones;
- configuración;
- últimos envíos.

## Decisiones

| Decisión | Alternativas descartadas | Por qué |
|---|---|---|
| **Categoría calculada** a partir de la fecha de nacimiento y la de la carrera; para filtrar y contar se traduce a rangos de fecha | Guardarla en la inscripción | Si la fecha de la carrera cambia, una categoría guardada queda mal sin avisar, y ese es justo el error del que se queja el cliente. Los rangos coinciden con el cálculo en Python en las 245.448 combinaciones probadas |
| **Dorsal**: índice único `(carrera, dorsal)` **solo cuando hay dorsal**, más un contador en la carrera bloqueada (`select_for_update`) | `Max(dorsal)+1`; secuencias del motor; índice único sin condición | `Max+1` falla con dos importaciones a la vez y las secuencias cambian según el motor. **SQL Server trata los NULL como iguales en un índice único**: sin la condición, dos inscripciones sin dorsal (en lista de espera) chocarían. El índice filtrado funciona en SQL Server, PostgreSQL y SQLite |
| **SQLite con transacciones `IMMEDIATE`** | Dejar el modo por defecto | En SQLite `select_for_update` no hace nada. Con dos altas a la vez, 3 de 47 comprobaciones fallaban con «database is locked» y se perdía un alta. Con `IMMEDIATE` esperan su turno. Solo afecta a desarrollo y a la CI |
| **Reimportación**: upsert por `(carrera, email normalizado)`; se compara antes de escribir y solo se actualiza desde el canal por el que llegó | Borrar y recrear; importar solo filas nuevas | Borrar cambia dorsales ya comunicados. Las filas no traen un identificador de la plataforma y el email es lo más estable que hay. Una noche sin cambios no escribe nada |
| **Quien desaparece del listado completo** queda marcado como ausente y la baja la confirma una persona. **Solo en las plataformas online** | Baja automática; ignorarlo; marcar también en la tienda | Un fichero cortado o de otra carrera daría de baja a cientos de personas con el dorsal ya comunicado. La tienda no manda un listado completo (sus altas en la app no están en su CSV): se marcaría a todo el mundo |
| **Clave de duplicado**: email en minúsculas y sin espacios (seguro); nombre y apellidos sin tildes + fecha de nacimiento (posible) | Solo email; búsqueda difusa | El email capta 3 de los 4 casos de las muestras y nombre+fecha capta el cuarto. No hay datos para calibrar una búsqueda difusa |
| **Mismo email repetido en un fichero con otros datos**: se queda la primera fila y la segunda sale en el informe como «repetida» con sus diferencias | Quedarse con la última sin avisar | En la media maratón, la fila 33 repite a una persona con otros datos: quedarse con una sin decirlo esconde un error de la plataforma |
| **Importación en segundo plano** (Celery): 202, progreso por lotes de 500 (cada uno en su transacción) y **cola por carrera** | Síncrona; una sola transacción; rechazar con 409 | Fuera de una transacción abierta no se ve el progreso. Encolar respeta el orden de llegada, que decide dorsales y lista de espera. Que solo haya una en marcha lo garantiza un índice único filtrado en la base de datos, no un cerrojo en memoria (hay 4 procesos de worker). Así no depende de los 30 s del proxy |
| **Filas inválidas**: no se guardan como inscripción; van al informe con su línea y motivo, separando las nuevas de las ya vistas | Guardarlas como inscripciones «inválidas» | Sin fecha no hay categoría y sin email no hay confirmación. Si no se separan las ya vistas, el maratón repetiría cada noche las mismas 80 |
| **Ingesta en etapas con un normalizador común**: origen → lector de formato (xlsx, csv) → mapeo de columnas por canal → **normalización única** (fechas de Excel o de texto, teléfono numérico o texto, email, talla) → validación de negocio. El alta de la tienda pasa por la misma normalización y validación | Un importador por canal; normalizar dentro de cada lector | Un proveedor nuevo con un formato conocido se configura (formato, codificación, separador, formato de fecha, alias de columnas) sin código; un formato nuevo es un lector, y un transporte nuevo (API, SFTP), un origen. Las reglas no se repiten en ningún sitio |
| **Normalizador abierto**: reglas por campo en un registro, limpieza común de texto, incidencias tipadas que nunca tumban el fichero, sin adivinar formatos de fecha; los valores desconocidos se agrupan en el informe y se resuelven configurando un alias o un formato | Un caso por cada error visto; adivinar fechas | Los errores nuevos llegarán con proveedores nuevos. Interpretar `03/04` como 4 de marzo o 3 de abril sin saberlo da categorías mal sin avisar |
| **Alta en tienda**: comprobación previa con `POST …/registrations/check/`; un email ya inscrito da 409 con el mismo texto, también si lo inscribió la propia tienda | Comprobar con GET; tratar el segundo alta como actualización | Con GET el email iba en la URL y salía en el log de acceso del servidor (comprobado). Tratarlo como actualización sobrescribiría los datos de otra persona sin preguntar |
| **El email de una inscripción de plataforma no se cambia en la app** (solo mayúsculas y minúsculas) | Dejar cambiarlo | El email es la clave de la reimportación: la noche siguiente daría de alta a la misma persona con otro dorsal. Se corrige en la plataforma |
| **Bajar el aforo no saca a nadie**; quitarlo (vacío) da dorsal a toda la espera | Sacar a los últimos confirmados | Un dorsal comunicado no se retira por un cambio de aforo. Lo que pasa con las bajas siguientes está en «Limitaciones» y en las preguntas |
| **Emails**: bandeja de salida en la base de datos y la misma `Idempotency-Key` en todos los intentos. 5xx, timeout y error de red se reintentan con espera creciente; un 429 espera `Retry-After` sin gastar intento; un 400 queda como fallido con motivo; un 401 para el lote. Ritmo propio por debajo del límite (15/s por defecto) | Enviar dentro de la petición; reintentar sin clave | Probado contra el simulador: **un timeout no significa que el mensaje no se aceptara**, y sin clave el reintento duplica el email. El proveedor solo recuerda la clave 24 h, así que «ya enviado» se guarda en nuestra base de datos. 20.000 emails a 15 por segundo son unos 22 min |
| **Proveedor de email intercambiable**: una interfaz con cuatro resultados (aceptado, reintentar, rechazado, error de configuración); reintentos y ritmo, fuera del adaptador | Llamar al notificador directamente | Cambiar de proveedor es una clase nueva y una variable de entorno |
| **Envío con botón y programado**: Celery beat late cada minuto y la tarea lee la configuración en la base de datos. Un registro de ejecuciones (`JobRun`) guarda cada envío; la fila «en marcha» es el cerrojo (índice único filtrado) | `django-celery-beat`; un cerrojo en Redis o en memoria | Sin dependencia nueva; cambiar la hora vale en el siguiente minuto; un latido de más no duplica nada gracias a la bandeja de salida y al cerrojo. Si un worker muere a mitad, el envío pasa a «caído» y el siguiente latido lo retoma |
| **Configuración en base de datos**: una fila con campos tipados y validados (envío automático, plantilla, ritmo, intentos, importaciones caídas) | Tabla clave-valor; reglas de negocio configurables | Una tabla clave-valor es todo texto y no se valida. Los secretos van en variables de entorno. Si los tramos de categoría fueran configurables, cambiarlos reescribiría las categorías de carreras pasadas |
| **Nada que dependa de un motor** (producción es SQL Server) | Funciones de PostgreSQL; `JSONField`; consultas con miles de valores en `IN` | Los índices únicos filtrados van sobre columnas no nulas; el orden de los NULL se fija con `Case`, porque cada motor los ordena distinto; las búsquedas por lote usan `IN` con 500 valores como máximo (SQL Server admite unos 2.100 parámetros) |
| **Dependencias**: solo `openpyxl`. Para el notificador, `urllib` de la librería estándar | pandas; requests | pandas es demasiado para leer 6 columnas, y una sola llamada POST no justifica otra dependencia |
| **Datos personales**: solo para gestionar la carrera; los logs no llevan emails ni teléfonos, solo el id de la inscripción y la línea del fichero. De una excepción se registra el tipo, no el texto | Registrar filas completas en los logs; borrar o anonimizar automáticamente | Son datos de hasta 20.000 personas por carrera. Plazos, consentimiento y anonimización los decide el cliente (preguntas 10–13) |
| **Subida de ficheros**: solo `.xlsx` y `.csv`, como máximo 20 MB, con mensaje claro si no | Sin límite | El maratón ocupa 1,4 MB: 20 MB es holgado y solo evita que un fichero equivocado llene el disco |

### Lo que dicen las muestras (medido)

| Muestra | Formato | Filas | Inválidas | Duplicados |
|---|---|---|---|---|
| Plataforma A, media maratón (xlsx) | Fecha como **número de serie de Excel**; 1 fila vacía | 41 | 5: menor de 16, email `x@`, sin apellidos, talla `XXXL`, sin fecha | 3: fila idéntica; email en mayúsculas y con espacios; mismo nombre, fecha y teléfono **con otro email** |
| Plataforma B, 10K (csv) | UTF-8, `,`, CRLF | 18 | 1: `31/02/1990` | 0 |
| Tienda, 10K (csv) | **cp1252, `;`**, cabeceras con mayúscula y tilde | 14 | 0 | **2 de 14 ya estaban en la Plataforma B** (una con el email en mayúsculas) |
| Plataforma B, maratón (csv) | UTF-8, `,`, CRLF | 20.000 | 80: 23 sin fecha, 20 sin `@`, 20 sin nombre, 17 talla `Única`. Ninguna menor de 16 | 19.920 válidas son **19.800 personas** |

Casos frontera de la media maratón (14/03/2027): una persona cumple 16 ese mismo día (entra, Junior) y otra cumple 35 ese mismo día (Veterano A, como en el ejemplo del enunciado).

## Preguntas para el cliente

1. **¿Desaparecer del listado de una plataforma es siempre una baja? ¿Puede llegar algún día un listado incompleto?** 
2. **Si alguien se inscribe por dos canales, ¿cuál vale y quién devuelve el dinero?** 
3. **La talla «Única» sale en 17 filas del maratón y no está en la lista.** ¿Existe? 
4. **¿Cuándo se manda la confirmación, con qué remitente y qué texto? ¿Se avisa también a quien entra en lista de espera, o a quien se da de baja después de recibir la confirmación?** 
5. **Aforo: las plataformas no mandan la fecha de inscripción. ¿Cortan ellas al llenarse?** 
6. **¿El aforo es por carrera o por categoría?** Supongo que por carrera.
7. **¿Cantidad estimada de usuarios?** Alta disponibilidad? Microservicios?
8. **¿Una baja libera la plaza aunque esté pagada?** 
9. **¿Las categorías, la edad mínima o las tallas cambian entre carreras o entre años?** Supongo que no.
10. **¿Los corredores han dado su consentimiento para recibir el email de confirmación, y dónde consta?** 
11. **¿Tenéis una política de privacidad, y qué dice sobre estos datos?** 
12. **¿Cuánto tiempo se guardan los datos de los corredores después de la carrera?** Politica de retención de datos?
13. **¿Hay que anonimizar algo?** 
14. **Si se baja el aforo por debajo de las confirmadas, ¿alguien pierde la plaza?** 
15. **Un posible duplicado (mismo nombre y fecha, otro email) recibe dorsal y ocupa plaza. ¿Debería esperar a que alguien lo revise?** Fuljo de revisión humana?
16. **¿Puede cambiar la fecha de una carrera con inscripciones?** Supongo que casi nunca. Solo se puede cambiar desde el admin de Django: las categorías se recalculan solas, pero no se vuelve a comprobar la edad mínima.

## Cómo lo he probado

**No he escrito tests nuevos.** Los 4 tests del backend y los 4 del frontend que traía el esqueleto siguen pasando. Lo explico en «Limitaciones».

Cada parte se ha dado por buena con un script de comprobación ejecutado dentro de los contenedores, contra PostgreSQL y el worker de Celery reales, y con cifras esperadas que salen de una **verdad de referencia hecha a mano**, no de la salida del propio código. Esa verdad son la edad, la categoría, las filas inválidas y los duplicados de las tres muestras pequeñas, contrastados con un script aparte: 0 discrepancias en 70 fechas. Los scripts quedan fuera del repo.

| Parte | Comprobaciones | Lo más importante |
|---|---|---|
| Normalizador y reglas | 55/55 | Las tres muestras pequeñas: 0 diferencias con la verdad de referencia. Formas que no están en las muestras (BOM, espacios raros, `mailto:`, `600000101.0`, `03/04/90` rechazada). 19 entradas raras sin excepción. Frontera: 16 justo ese día → Junior; 35 → Veterano A |
| Lectores | 38/38 | xlsx 41 registros con la fecha de Excel; tienda cp1252 con `;`; maratón 20.000; errores del fichero con mensaje (falta una columna, formato equivocado, xlsx roto) |
| Modelo | 22/22, PostgreSQL y SQLite | Dos inscripciones sin dorsal conviven; dorsal, email y posición de espera repetidos → error de integridad en los dos motores |
| Inscribir, aforo y baja | 47/47, PostgreSQL y SQLite | Aforo 20 en el 10K: B → 1–17, tienda → 18–20 y 9 en espera. Baja del 5 → entra Íñigo con el 21. Dos altas a la vez → dorsales distintos (con una pausa forzada entre leer y guardar). Sin bloqueo, el mismo script da `IntegrityError`: la prueba detecta el fallo |
| Importación | 35/35 | Media maratón: 33 altas (una como posible duplicado), 5 rechazadas, 2 repetidas, 1 vacía; categorías iguales a la referencia. 10K: 29 personas, dorsales 1–29, 2 ya inscritas sin segundo dorsal. Reimportar: 0 escrituras y mismos dorsales. Falta una fila → ausente; vuelve → se quita la marca. Fallo provocado a mitad → «10 de 18 filas»; reimportar lo completa. **Maratón: 19.800 inscripciones y 80 rechazadas en 20,2 s; reimportación en 8,1 s.** Segunda importación de la misma carrera → en cola. Logs sin un solo email ni teléfono |
| API de inscripciones | 62/62 | Búsqueda con y sin tildes, por email y por dorsal; check y alta de Claudia → mismo aviso y 409; 400 con los motivos del dominio; cuatro altas a la vez (dos con el mismo email) → 201×3 + 409. **Maratón: 396 páginas, 4 consultas por página** (sin N+1), 42–95 ms |
| Emails | 58/58 | Con un proveedor falso: reintento con la misma clave, 429 sin gastar intento, fallida con motivo, 401 para el lote, dos envíos a la vez no duplican. **Contra el simulador real: 29 confirmadas del 10K → 29 mensajes, uno por clave; reenviar → siguen 29.** Ráfaga a 40/s: 8 respuestas 429 y 80 mensajes, uno por clave |
| Envío programado | 24/24 + 9/9 contra el simulador | Antes de la hora no hace nada; a la hora, un solo envío en el día; con otro en marcha no arranca otro; un envío caído se retoma; `{dni}` en la plantilla → 400; la plantilla guardada es la que llega al simulador |
| Arreglos de la revisión | 22/22 | Y, después, todo lo anterior otra vez sin fallos |

Antes de cada commit han pasado las siete comprobaciones en Docker: pytest, `ruff check`, `ruff format --check`, `makemigrations --check`, `npm test`, `npm run lint` y `npm run build`. pytest también se ha pasado en SQLite, que es el motor de la CI.

## Limitaciones conocidas

**Lo más importante:**
- **No hay tests nuevos.** Las comprobaciones de arriba se hicieron con scripts que no están en el repo, así que la CI solo pasa los tests del esqueleto. Es lo primero que haría (ver «Oportunidades de mejora»).
- **Sin autenticación**, como dice el enunciado, así que no se sabe quién hizo cada cosa (quién dio una baja o cambió el aforo).

**Inscripciones:**
- Una inscripción dada de baja no se puede volver a dar de alta con el mismo email (409): no hay «reactivar».
- Corregir el nombre o la fecha de nacimiento no recalcula la marca de posible duplicado.
- **Corregir el email después de enviar la confirmación no la reenvía** a la dirección nueva.
- La **posición en la lista de espera no se recalcula**: tras promociones o bajas, «n.º 10» puede ser la tercera en la cola. El orden sí es el correcto.
- **Quitar el aforo** (dejar el campo vacío) da dorsal a toda la lista de espera de golpe y sin pedir confirmación. No se puede deshacer.
- **Bajar el aforo por debajo de las confirmadas**: nadie pierde la plaza y el panel lo enseña («N por encima del aforo»), pero el diálogo no avisa antes de guardar, y una baja que no saca a nadie de la espera no explica por qué.
- Quien se da de baja en la app y sigue en el listado de su plataforma sale cada noche como «sin cambios», sin aviso (pregunta 16).
- Cambiar la fecha de la carrera desde el admin no vuelve a comprobar la edad mínima (pregunta 17).
- La búsqueda es un GET: si se busca por email, el email sale en el log de acceso del servidor. En producción habría que quitar la query string de ese log o buscar por POST.
- No hay límite inferior para la fecha de nacimiento: una errata como `1900` entra sin aviso.

**Emails:**
- Un proveedor que conteste 429 sin fin no gasta intentos: se sigue esperando mientras diga «espera».
- Una notificación pendiente que deja de tocar (baja, posible duplicado) se queda pendiente y cuenta como «omitida» en cada envío. «Omitidas» también incluye las que otro envío simultáneo cogió antes.
- Un mensaje que agota los intentos sin respuesta queda como «fallido», aunque el proveedor pudiera haberlo aceptado. Reintentarlo es seguro: usa la misma clave.
- Una carrera que se celebra hoy todavía recibe confirmaciones.
- Un cambio de dorsal no generaría un email nuevo.
- Para no pisar un reintento reprogramado, se compara la hora del siguiente intento con la guardada por igualdad.

**Envío programado:**
- Si un envío programado acaba con error, ese día no se reintenta solo: se ve en Configuración y se envía con el botón. Así no se insiste cada minuto contra un proveedor que falla.
- El envío programado corre dentro del latido y ocupa un proceso del worker mientras dura (unos 22 min para 20.000 emails).

**Producción:**
- **SQL Server**: cada lote de 500 filas bloquea la carrera menos de un segundo. Con el aislamiento por defecto de SQL Server, las lecturas de esa carrera esperan ese rato; con `READ_COMMITTED_SNAPSHOT` activado en la base de datos, no esperan. No lo he probado en SQL Server.
- El límite de 20 MB se comprueba después de recibir el fichero. En producción conviene que lo corte también el proxy.

## Oportunidades de mejora

### 1. Tests de integración por caso de uso

El valor de la aplicación está en el flujo entero, no en las piezas sueltas. Un fichero real entra, se normaliza, se inscribe con la carrera bloqueada, se reparte el dorsal o la espera, y se confirma por email. Por eso, antes que tests unitarios, pondría **un test por caso de uso** que recorra ese flujo por la API, contra la base de datos y con las tareas de Celery ejecutándose en el propio proceso. Las cifras esperadas saldrían de la verdad de referencia hecha a mano, copiada al repo como datos de prueba, nunca de la salida del código. Los scripts de comprobación ya tienen los casos y las cifras: es pasarlos a pytest.

| Caso de uso | Qué comprueba el test |
|---|---|
| **Importar el listado de una plataforma** | Las cuatro muestras de `samples/`: altas, rechazadas con línea y motivo, repetidas, vacías y categorías iguales a la referencia. En la media maratón: 33 altas, 5 rechazadas, 2 repetidas, 1 vacía |
| **Reimportar el listado completo de cada noche** | Mismo fichero → 0 escrituras y mismos dorsales. Una fila que falta → ausente. Confirmar su baja → entra la primera en espera. Fichero cortado a mitad → «X de Y guardadas» y reimportar lo completa |
| **Importar la tienda después de una plataforma** | 10K: 29 personas con dorsales 1–29; Claudia y Álex como «ya inscritas» con sus diferencias, sin un segundo dorsal |
| **Dar de alta en el mostrador** | La comprobación previa avisa «ya inscrita»; el alta con ese email da 409 con el mismo texto; con el aforo lleno, el alta va a la lista de espera; los datos inválidos dan 400 con el motivo |
| **Gestionar el aforo** | Con aforo 20: dorsales 1–20 y 9 en espera. La baja del 5 da el 21. Subir el aforo hace entrar a las siguientes. Bajarlo no saca a nadie. Una persona ausente no sale de la espera |
| **Buscar el día de la carrera** | Nombre con y sin tildes, email y dorsal exacto. Número de consultas fijo por página (`django_assert_num_queries`) |
| **Mandar las confirmaciones** | Un proveedor falso con un guion de respuestas (500, timeout, 429, 400, 401): un solo mensaje por clave, el 429 no gasta intento, la fallida guarda su motivo, el 401 para el lote. Uno contra el simulador real, arrancado por el propio test con una semilla fija: 29 confirmadas → 29 mensajes |
| **Envío programado** | `run_due_jobs` con la hora inyectada: antes de la hora no hace nada, a la hora envía una sola vez al día, con otro en marcha no arranca, un envío caído se retoma |
| **Altas a la vez** | Dos altas en paralelo dan dorsales distintos. Necesita PostgreSQL en la CI (hoy usa SQLite, donde las transacciones se serializan): un servicio más en el workflow |

Tests unitarios, solo donde la lógica es densa y barata de probar en tabla:
- el normalizador, con las formas raras;
- la categoría en los días frontera (16 y 35 años justo el día de la carrera);
- la traducción de categorías a rangos de fecha.

En el frontend, tests de pantalla de los dos flujos críticos, con la API simulada:
- importar y leer el informe;
- alta en el mostrador con el aviso antes de guardar.

Una prueba de punta a punta en navegador (Playwright) daría más confianza, pero es una dependencia nueva: la consultaría antes.

### 2. Producto

- **Proteger el aforo**:
  - pedir confirmación antes de quitarlo, diciendo cuántas personas recibirán dorsal;
  - avisar al bajarlo por debajo de las confirmadas;
  - explicar en el aviso por qué una baja no saca a nadie de la espera.
- En el informe de importación, **avisar de quien está de baja en la app y sigue en el listado** de su plataforma.
- Enseñar la **posición real en la lista de espera** (cuántas tiene delante).
- Según lo que conteste el cliente:
  - aforo por categoría;
  - posibles duplicados sin plaza hasta revisarlos;
  - aviso de edad al cambiar la fecha de la carrera.
- «**Fusionar**» posibles duplicados y «**reactivar**» una baja.
- **Ampliar el sistema de emails a otros casos de uso.** Hoy solo se manda la confirmación con dorsal. Candidatos:
  - aviso al entrar en la lista de espera, con la posición;
  - aviso al salir de la espera con dorsal (hoy recibe la confirmación normal, sin decirle que venía de la espera);
  - aviso de baja a quien ya tenía la confirmación;
  - reenvío de la confirmación cuando se corrige el email;
  - aviso a todos los corredores si cambia la fecha o el lugar de la carrera;
  - recordatorio unos días antes de la carrera, con el dorsal y la recogida.

  La base ya está: bandeja de salida, reintentos, idempotencia, ritmo, envío programado y proveedor intercambiable. Faltaría un tipo en cada notificación (y en su clave de idempotencia), una plantilla por tipo en Configuración y decidir con el cliente cuáles quiere (pregunta 4).
- **Exportar dorsales** para el día de la carrera.
- **Integración por API o SFTP** con alguna plataforma concreta: es un origen nuevo delante del mismo normalizador.

### 3. Operación y producción

- **Autenticación y registro de quién hizo cada cosa** (bajas, cambios de aforo, correcciones), en cuanto el cliente la quiera.
- **Probar en SQL Server** con `READ_COMMITTED_SNAPSHOT` activado, para que las lecturas no esperen a los lotes de importación.
- El límite de subida también en el proxy.
- El envío programado en una cola propia de Celery, para que un envío de 20 minutos no ocupe un proceso de los que importan.
- Avisos a la organización cuando un envío o una importación acaban con error, en vez de esperar a que alguien abra la pantalla.

## Uso de IA

He trabajado con **Claude Code** con un ciclo por pasos: cada paso termina, se me cuenta y no se sigue hasta que yo lo reviso.

### Estructura

| Rol | Quién | Qué hizo |
|---|---|---|
| **Analizador** | Sesión principal | Leyó el enunciado y el esqueleto, midió las muestras con scripts desechables, probó el simulador del proveedor, preparó la verdad de referencia y propuso decisiones con sus alternativas |
| **Orquestador** | Sesión principal | Llevó el plan (tareas con criterios de aceptación medidos sobre `samples/`) e implementó la mayoría de tareas. De lo que hicieron los subagentes, leyó el diff entero. Pasó las comprobaciones, escribió los scripts de comprobación e hizo los commits |
| **Subagentes** | Dos, cada uno en su propio worktree | Uno hizo el frontend de importación e inscripciones; otro, el envío de emails. Se hicieron en paralelo con la configuración, contra un contrato de API fijado antes |
| **Revisor** | Un subagente independiente, solo lectura | Revisó la rama completa sin haber escrito el código |
| **Yo** | — | Decidí el alcance y cada decisión de diseño, revisé cada paso y di el visto bueno para seguir |

### Cómo se ha aplicado

- **Análisis**, en la sesión principal, sin subagentes. Lo revisamos juntos en varias vueltas. Produjo:
  - la medición de las 4 muestras;
  - el comportamiento real del simulador del proveedor (500, respuestas lentas que sí se aceptan, 429, idempotencia);
  - la verdad de referencia fila a fila de las muestras pequeñas (0 discrepancias en 70 fechas);
  - el análisis, el plan y el borrador de este documento.
- **Desarrollo**. El plan decía un subagente por tarea. Lo cambié sobre la marcha por consumo: las tareas pequeñas y medianas, la importación incluida, las hizo el orquestador en la sesión principal. A subagentes fueron el frontend y los emails, en paralelo y cada uno en su worktree.
- **Revisión**. El revisor encontró 12 problemas (ninguno grave, 4 medios). El orquestador reprodujo los principales antes de clasificarlos. Yo decidí arreglar 9 y dejar 3 como limitaciones.


## Tiempo dedicado

El análisis se hizo el 13/11 (1.5h) y el desarrollo, el 17/11 (1.5h de desarrollo + 1 de documentación).
