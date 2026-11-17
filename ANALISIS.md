# ANÁLISIS · Prueba Dorsal

Escrito el 13/11/2026, antes de escribir código. Cada cifra lleva su muestra. La verdad de referencia (edad, categoría,
filas inválidas y duplicados de las muestras pequeñas) se hizo a mano, y las mediciones, con scripts desechables que no
son código del producto.

Fechas de carrera que uso, tomadas de `seed_demo` (mismo nombre de carrera que en `docs/reglas-de-negocio.md`):
Media Maratón del Río **14/03/2027**, 10K Nocturna del Puerto **19/06/2027**, Maratón de la Ciudad **07/11/2027**.

---

## §1 · Qué pide el cliente, priorizado

| # | Necesidad | Prioridad | Valor | Riesgo técnico | Por qué ahí |
|---|---|---|---|---|---|
| 1 | Importar el listado de una carrera (xlsx / csv / csv de tienda) | **Mínimo del enunciado** | Máximo | Alto: 3 formatos, codificaciones, 20.000 filas frente a 30 s | Sin esto no hay nada |
| 2 | Ver inscripciones con **categoría** y **dorsal** | **Mínimo del enunciado** | Máximo | Medio: edad el día de la carrera, dorsal único con 5 usuarios | «Siempre se queja alguien» |
| 3 | **Reimportar** el listado completo cada noche sin romper nada | Implícito en el mínimo | Alto | Alto | Las plataformas mandan el listado completo, no el incremento: si no es idempotente, el día 2 ya falla |
| 4 | Filas inválidas visibles (menor de 16, talla, email, vacíos) | Implícito en el mínimo | Alto | Bajo | 80 de 20.000 filas en el maratón, 5 de 41 en la media |
| 5 | **Detectar duplicados** dentro y entre canales | Alto | Alto | Medio | Lo pide el cliente; sale casi gratis si la clave de importación es buena |
| 6 | **Buscar** por nombre o dorsal | Alto | Alto el día de carrera | Bajo | Barato sobre la lista; tiene que ir rápido con 20.000 |
| 7 | **Emails** de confirmación con un proveedor que falla | Medio | Medio | Alto, y es justo lo que el enunciado pone a prueba | El simulador falla a propósito: reintentos e idempotencia bien hechos |
| 8 | **Aforo y lista de espera** | Bajo | Medio («algunas carreras») | Medio: interactúa con dorsales y reimportación | Después del resto; versión mínima |

---

## §2 · Lo que dicen los datos (medido)

### Formato

| Muestra | Codificación | Separador | Fin de línea | Cabecera | Fecha | Filas de datos |
|---|---|---|---|---|---|---|
| `plataforma_a_media_maraton.xlsx` | xlsx, 1 hoja «Inscripciones», cadenas en línea (sin sharedStrings) | — | — | `nombre … talla_camiseta` | **celda numérica** (serie Excel) con formato `DD/MM/YYYY`; 40 de 41 filas | 41 (A1:F42), una vacía |
| `plataforma_b_10k.csv` | UTF-8 sin BOM | `,` | CRLF (19 de 19 líneas) | igual que las reglas | texto `dd/mm/aaaa` en 18 de 18 | 18 |
| `tienda_10k.csv` | **cp1252/latin-1** (no es UTF-8: falla en el byte 43, «é» de «Teléfono»); sin bytes 0x80–0x9F, así que las dos son equivalentes aquí | **`;`** | CRLF (15 de 15) | **`Nombre;Apellidos;Email;Fecha_nacimiento;Teléfono;Talla_camiseta`**: mayúscula inicial y tilde | texto `dd/mm/aaaa` en 14 de 14 | 14 |
| `plataforma_b_maraton.csv` | UTF-8 sin BOM | `,` | CRLF (20.001 de 20.001) | igual que las reglas | `dd/mm/aaaa` en 19.977; **vacía en 23** | 20.000 |

Ninguna muestra tiene comillas, campos con separador dentro, ni espacios sobrantes salvo un email del xlsx.
Teléfono: celda numérica en el xlsx (pierde ceros a la izquierda si los hubiera; ningún 0 inicial visto) y una celda de texto
`+34 600 000 106` (fila 25); vacío en 5.852 de 20.000 filas del maratón.

### Filas inválidas

| Muestra | Inválidas | Detalle (fila del fichero) |
|---|---|---|
| media maratón (41) | **5** + 1 vacía | 4 menor de 16 (15 años) · 20 email `sergio.navarro@` · 28 apellidos vacíos · 37 talla `XXXL` · 41 fecha vacía · 32 fila vacía |
| plataforma B 10K (18) | **1** | 11 fecha inexistente `31/02/1990` |
| tienda 10K (14) | **0** | — (una con email en mayúsculas, fila 11: válida) |
| maratón (20.000) | **80** | 23 fecha vacía · 20 email sin `@` (p. ej. `celia.prieto656example.org`) · 20 nombre vacío · 17 talla `Única`. **Ninguna** menor de 16 (edades de 17 a 72). Las 80 tienen una fila gemela válida (mismo nombre o email): **0 corredores se pierden** al rechazarlas |

Casos frontera de edad, en la media maratón: fila 11 cumple **16 el mismo día** (entra, Junior), fila 12 cumple **35 el
mismo día** (Veterana A, es el ejemplo del enunciado), fila 2 cumple 35 seis días después (Senior). En el maratón,
64 de 20.000 cumplen años el día de la carrera.

### Duplicados

| Dentro de… | Medido |
|---|---|
| media maratón | 3 casos: fila 42 = fila 27 idéntica · fila 33 = fila 25 con email `' NOA.MARTIN@example.com '` (mayúsculas, espacios), apellido sin tilde y sin teléfono · **fila 38 vs 26: mismo nombre, fecha y teléfono, email distinto** (`igomez85@example.net` vs `ivan.gomez@example.com`): lo único que no captura el email |
| plataforma B 10K | 0 |
| tienda 10K | 0 |
| maratón | 19.920 válidas → **19.800 personas** (por email normalizado y por nombre+fecha salen las mismas 19.800). 62 grupos idénticos, 56 que solo cambian el email a MAYÚSCULAS, 3 personas que salen 3 veces. **0** casos de un email con dos personas distintas y **0** de una persona con dos emails distintos (entre filas válidas) |
| **entre canales (10K)** | **2 de 14** filas de tienda están también en plataforma B: Claudia Benítez (fila 10 = B fila 10, idéntica) y Álex Ruiz (fila 11 = B fila 2, email `Alex.Ruiz@…` en mayúsculas). 10K = **29 personas** (17 válidas de B + 12 nuevas de tienda) |

Conclusión: la clave **email en minúsculas y sin espacios** captura todos los duplicados vistos salvo uno (Iván, fila 38),
que solo sale por **nombre normalizado (sin tildes) + fecha**.

### Volumen frente a los 30 s

El maratón son 20.000 filas y 1,4 MB. Parsear y validar en Python es cuestión de segundos (sin medir todavía en
Django: se mide en la tarea T5). El riesgo no es el parseo, es escribir 20.000 filas con inserciones fila a fila y,
sobre todo, **mandar 20.000 emails**: a 20 peticiones/s del límite del proveedor son **≥ 1.000 s (17 min)**. Eso
no cabe en ninguna petición HTTP.

### El proveedor de emails, medido contra el simulador (semilla 1)

- 100 envíos espaciados: **90 × 202, 10 × 500** y 10 respuestas tardaron > 2 s (3 s): 10 % de fallos y 10 % de lentitud, como dice la doc.
- Un **500 no guarda la clave**: reintentar con la misma `Idempotency-Key` envía de verdad. Tras reintentar las 100 claves hasta 202, el registro tiene **100 mensajes, ni uno de más**.
- Repetir una clave aceptada devuelve `202` con `Idempotent-Replayed: true` y no envía.
- Con **timeout de 1 s**, 4 de 40 peticiones cortaron… **y el mensaje quedó aceptado igualmente**. Sin clave, reintentar ahí duplica el email.
- Ráfaga de 40 en paralelo: **20 × 429** (`Retry-After: 1`), 18 × 202, 2 × 500. El 429 llega antes que la comprobación de idempotencia.
- Sin `Authorization`: 401. Email sin `@`: 400 (el simulador solo comprueba la `@`).
- Recuerda las claves mientras está en marcha (el real, 24 h): **la fuente de verdad de «ya enviado» tiene que ser nuestra base de datos**, no la clave.

---

## §3 · Casos raros y qué hago con cada uno

| Caso | Visto en | Qué hago |
|---|---|---|
| Codificación cp1252 | tienda (14/14) | Intento UTF-8 (quitando BOM); si falla, cp1252. Nada de adivinar con librerías |
| Separador `;` | tienda | Detecto el separador en la línea de cabecera (`;` o `,`) |
| Cabeceras con mayúscula y tilde | tienda | Normalizo cabeceras (minúsculas, sin tildes) y mapeo por nombre; si falta una columna obligatoria, error claro del fichero entero |
| Fecha como número de serie Excel | xlsx (40/41) | openpyxl la da como fecha; acepto también texto `dd/mm/aaaa` en el xlsx por si acaso |
| Fecha inexistente `31/02/1990` | B 10K fila 11 | Fila rechazada: «fecha de nacimiento no válida» |
| Fecha vacía | maratón 23, media 1 | Fila rechazada |
| Menor de 16 el día de la carrera | media fila 4 | Fila rechazada con la edad en el motivo |
| Cumple 16 o 35 justo ese día | media filas 11 y 12 | Edad cumplida ese día: entra / sube de categoría (como el ejemplo del enunciado) |
| Email mal (`x@`, sin `@`) | media 1, maratón 20 | Rechazada. Validación de Django (`EmailValidator`), más estricta que la del proveedor |
| Email en mayúsculas o con espacios | maratón 56, media 1, tienda 1 | Se guarda tal cual para mostrar; la clave es `email_norm` = minúsculas y sin espacios |
| Talla fuera de lista (`XXXL`, `Única`) | media 1, maratón 17 | Rechazada (las reglas solo admiten XS–XXL). `Única` → pregunta al cliente |
| Talla en minúsculas | 0 vistas | Acepto `m` como `M` (normalizo a mayúsculas) |
| Nombre o apellidos vacíos | maratón 20, media 1 | Rechazada |
| Fila totalmente vacía | media fila 32 | Se ignora y se cuenta aparte («1 fila vacía»), no es un error |
| Teléfono numérico / con prefijo | xlsx | Texto libre: entero → `str(int)`; texto, tal cual |
| Fila idéntica repetida en el mismo fichero | media 1, maratón 62 grupos | Una sola inscripción; contada como «repetida en el fichero» |
| Mismo email en otro canal | tienda 2 de 14 | **Duplicado**: no crea segunda inscripción ni segundo dorsal; queda marcada «también inscrita por tienda» para revisar |
| Mismo nombre + fecha, email distinto | media fila 38 | **Posible duplicado**: inscripción propia con su dorsal, marcada y enlazada a la otra para que decida una persona |
| Reimportar el mismo listado | (el enunciado) | 0 altas, 0 cambios, dorsales iguales |
| Listado nuevo con cambios (talla, teléfono) | no visto (no hay dos noches de muestra) | Se actualiza la inscripción si llegó por ese mismo canal; el dorsal no cambia. Si llegó por otro canal, se muestra la diferencia sin sobrescribir |
| Alguien que desaparece del listado de su plataforma | **no lo hemos visto** (no hay dos noches de muestra) | Como el listado es completo (`docs/reglas-de-negocio.md`), es señal de baja en la plataforma, pero **no se da de baja sola**: queda marcada «no aparece en el listado de Plataforma B desde el dd/mm» y la organización confirma la baja con un botón. Si vuelve a aparecer, la marca se quita sola. Solo cuenta para inscripciones que llegaron por ese canal |
| Mismo email con dos personas distintas | **0 vistos** en 19.920 filas válidas del maratón | Supongo que no ocurre; si ocurre, la segunda se trataría como la primera. Pregunta |
| Columnas en otro orden / columna extra | no visto | Mapeo por nombre de cabecera: funciona igual. Columnas extra, ignoradas |
| Fichero muy grande o que no es una hoja de cálculo | no visto | Se rechaza al subir, con mensaje claro: solo `.xlsx` y `.csv`, y un tope de 20 MB. Es holgado: el maratón ocupa 1,4 MB con 20.000 filas, y 20 MB dan para unas 280.000. El tope solo sirve para que un error de fichero no llene el disco |

---

## §4 · Modelo de datos y decisiones clave

```
Race (existe)  + capacity (nullable: null = sin límite) + next_bib (int, por defecto 1)
Channel        code · name · kind (plataforma_online | presencial) · format (xlsx | csv)
               · encoding (vacío = detectar) · delimiter (vacío = detectar)
               · date_formats (lista ordenada; por defecto dd/mm/aaaa)
ChannelColumn  channel · source_header · field (nombre | apellidos | email | fecha_nacimiento | telefono | talla)
               Solo si un proveedor usa otros nombres de columna; sin filas, valen los nombres de las reglas
ValueAlias     channel (nullable = todos) · field · source_value · value  (p. ej. talla «2XL» → XXL)
Registration   race · first_name · last_name · email · email_norm · birth_date · phone · shirt_size
               · channel (FK: por dónde llegó primero) · also_channels (canales donde volvió a aparecer)
               · status (confirmada | en_espera | baja) · bib (nullable) · waitlist_position (nullable)
               · possible_duplicate_of (FK nullable) · search_text (nombre normalizado)
               · missing_since (fecha nullable: no aparece en el último listado de su canal) · created_at / updated_at
               UniqueConstraint(race, email_norm)
               UniqueConstraint(race, bib, condition=bib IS NOT NULL)
ImportBatch    race · channel · file · status (en_cola | procesando | hecho | error) · total_rows · processed_rows
               · contadores (altas, en espera, actualizadas, sin cambios, repetidas, ya inscritas, rechazadas, vacías)
               · error · fechas
               UniqueConstraint(race, condition=status = procesando)
ImportIssue    batch · line · kind (rechazada | ya_inscrita | posible_duplicada | ausente) · is_new (no estaba en la
               importación anterior del mismo canal) · message · differences · raw
Notification   registration · idempotency_key (único) · status (pendiente | enviando | enviada | fallida)
               · attempts · next_attempt_at · last_error · provider (nombre) · provider_id · sent_at
Settings       fila única (pk=1): auto_send_enabled · auto_send_time (hora local) · email_subject · email_body
               · send_rate_per_second · max_attempts · import_stale_minutes · updated_at
JobRun         job (envio_programado | ...) · started_at · finished_at · result (ok | idle | locked | error) · summary
```

| Decisión | Elegido | Descartado | Por qué |
|---|---|---|---|
| **Categoría** | **Calculada** (función pura `category_for(birth_date, race_date)` en `domain/`); para filtrar por categoría se traduce a rangos de `birth_date` en la consulta | Guardada en la fila | La fecha de la carrera puede cambiar y una categoría guardada quedaría mal sin avisar: justo el error del que se queja el cliente. Calcular es O(1) y filtrable por rangos de fecha sin SQL especial |
| **Dorsal único con 5 usuarios a la vez** | `UniqueConstraint` condicional (`bib IS NOT NULL`) como red, y **reserva por bloques**: dentro de la transacción de importación, `select_for_update()` sobre la carrera y `next_bib += n` | `Max(bib)+1` por fila; secuencias de la base de datos; `UniqueConstraint` sin condición | `Max+1` falla con dos importaciones a la vez. Las secuencias son distintas en cada motor. **SQL Server trata los NULL como iguales en un índice único**: sin condición, dos inscripciones sin dorsal chocan. El índice filtrado existe en SQL Server, PostgreSQL y SQLite. `select_for_update` lo soporta mssql-django (UPDLOCK) y PostgreSQL; SQLite lo ignora pero serializa las escrituras igualmente |
| **Reimportación del listado completo** | Las plataformas mandan cada noche el listado **completo** (`docs/reglas-de-negocio.md`, decidido 13/11). **Upsert** por `(race, email_norm)`: se actualiza solo si cambió algo y solo desde el canal por el que llegó; el dorsal no se toca. Repetir el fichero da 0 cambios. Se compara antes de escribir, así que una noche sin cambios en el maratón no reescribe 19.800 filas. **Ausencias**: quien llegó por ese canal y no está en el listado nuevo queda marcado `missing_since`, sin baja automática; la baja la confirma una persona. **Avisos sin repetir**: los avisos de «ya inscrita» y las filas rechazadas que ya salieron en la importación anterior del mismo canal se cuentan aparte («80 rechazadas, 0 nuevas») | Borrar y recrear; importar solo las filas nuevas; baja automática de quien falte | Borrar cambia dorsales ya impresos. Las filas no traen identificador de la plataforma; el email es lo más estable. Una baja automática con un fichero cortado, de otra carrera o de un día con fallos en la plataforma daría de baja a cientos de corredores con el dorsal ya comunicado; marcar y confirmar cuesta un clic. Sin avisos «nuevos», el informe repetiría cada noche las mismas 80 rechazadas del maratón y nadie lo leería |
| **Clave de duplicado** | **Seguro**: `email_norm` (minúsculas, sin espacios) dentro de la carrera, en cualquier canal. **Posible**: nombre y apellidos normalizados (sin tildes, minúsculas) + fecha de nacimiento | Solo email; solo nombre+fecha; búsqueda difusa | El email capta 3 de los 4 casos vistos; nombre+fecha capta el 4.º (Iván). Lo difuso da falsos positivos y no hay datos para calibrarlo. El posible duplicado no se fusiona solo: decide una persona. **Alerta** (decidido 13/11): el informe de importación abre con «N personas ya estaban inscritas por otro canal: no se les ha dado otro dorsal», con la lista y **las diferencias de datos** entre lo que ya teníamos y lo que trae el nuevo canal (talla, teléfono…); esos datos **no se sobrescriben** desde otro canal, se muestran para que la organización hable con el corredor. La inscripción lleva una marca visible en la tabla. Para evitarlo en origen, la búsqueda también encuentra por email, y la tienda puede comprobar en la app si alguien ya está inscrito antes de apuntarlo |
| **Importación en segundo plano, con progreso y en cola** | Celery: `POST` sube el fichero, crea `ImportBatch` y responde **202**. **Progreso visible**: `total_rows`/`processed_rows`; el frontend sondea y muestra fase y porcentaje. Leer y validar todo sin escribir → escribir en lotes de 500, **cada lote en su transacción** (si no, el progreso no se ve desde fuera). Si falla a mitad: «X de Y guardadas», y reimportar lo completa. **Solapes: se encolan** (decidido 13/11): una segunda importación de la misma carrera queda `en_cola` y arranca al terminar la anterior, en orden de subida; la garantía es `UniqueConstraint(race, condition=status=procesando)` en la base de datos, y el paso de una a la siguiente se decide con la carrera bloqueada (`select_for_update`) para que dos workers no arranquen a la vez. Carreras distintas, en paralelo. Un batch sin progreso 10 min se da por caído y libera la cola | Síncrona; una transacción para todo; rechazar con 409; cerrojo en memoria | Hoy el maratón quizá quepa en 30 s, pero sin margen con SQL Server en red y 5 usuarios. Una transacción única oculta el progreso. Rechazar obliga al usuario a esperar y reintentar; encolar no, y el orden importa (dorsales y lista de espera por orden de llegada). Un cerrojo en memoria no sirve con 4 procesos de worker. Sin Docker (opción B del README; aquí se usa Docker, decidido 17/11) la tarea corre en la petición y el progreso salta a 100 %: para verlo de verdad, worker local con el broker `filesystem://` de kombu (sin RabbitMQ) |
| **Envío de emails robusto** | Bandeja de salida en BD (`Notification`), una fila por mensaje lógico. `Idempotency-Key = confirmacion-{registration_id}-{bib}` en **todos** los intentos. Por respuesta: **202** → enviada (guardo `provider_id`); **5xx, timeout, error de red** → reintento con espera exponencial con jitter (máx. 6 intentos) y la misma clave; **429** → espera exactamente `Retry-After` y no cuenta como intento; **400** → fallida sin reintento, con el motivo; **401** → se para todo el lote (configuración), sin quemar intentos. Ritmo propio por debajo de 20/s. Timeout 10 s (las lentas tardan 3 s). Estado `enviando` con hora: si el worker muere a mitad, otro lo retoma con la misma clave. Antes de enviar se comprueba en BD que no está `enviada` (la clave solo dura 24 h en el proveedor). Las fallidas se ven en la app con motivo y botón «reintentar» | Enviar en la petición; reintentar sin clave; fiarse solo de la clave; reintentos infinitos | Medido: un timeout no significa que no se aceptara, y sin clave se duplica; un 500 no guarda la clave. 20.000 emails a 20/s son ≥ 17 min |
| **Envío: cuándo** | **Las dos cosas** (decidido 13/11): botón «Enviar confirmaciones pendientes (N)» por carrera y **envío programado** configurable. Los dos llaman al mismo caso de uso y mandan lo mismo: confirmadas con dorsal, sin email enviado y sin marca de posible duplicado, en carreras que aún no se han celebrado | Solo botón; solo automático al importar | El botón para cuando se quiere ya; lo programado para no depender de que alguien se acuerde. Al compartir la bandeja de salida, que coincidan no duplica nada |
| **Envío programado (Celery beat)** | **Beat late cada minuto** con una tarea fija; la tarea lee `Settings` y decide si toca (activado y pasada la hora de hoy sin ejecución hecha hoy). Cerrojo por trabajo y registro en `JobRun` con `ok / idle / locked / error` y resumen en cifras. Servicio `beat` nuevo en docker-compose (una sola instancia). Con Docker, servicio `beat` en docker-compose; sin Docker (opción B): `celery beat` + worker con el broker `filesystem://`, o el comando `manage.py run_due_jobs` para lanzar el latido a mano | `django-celery-beat` (DatabaseScheduler); horario fijo en `beat_schedule` | Cambiar la hora en la vista vale al instante, sin reiniciar beat ni sincronizar tablas de otro. Sin dependencia nueva y sin tablas cuyo soporte en SQL Server no he comprobado. Un latido de más no hace daño: la bandeja de salida es idempotente y el cerrojo evita dos envíos a la vez |
| **Configuración en BD** | Modelo `Settings` de **una sola fila con campos tipados** y validación al guardar, editable en una vista «Configuración»: envío automático (sí/no, hora), plantilla (asunto y cuerpo con `{nombre}`, `{dorsal}`, `{carrera}`, `{fecha}`; un marcador desconocido da error al guardar), ritmo (emails/s), intentos máximos, minutos para dar por caída una importación. Se lee al empezar cada tarea, sin caché | Tabla clave-valor; todo en variables de entorno; reglas de negocio configurables | Clave-valor es todo texto y sin validación. **Secretos y URL del proveedor siguen en variables de entorno**: dependen del entorno y no deben verse en una pantalla. Categorías, edad mínima y tallas se quedan en código: como la categoría se calcula al vuelo, cambiar los tramos cambiaría la de carreras ya hechas; si el cliente las quiere configurables, habría que guardarlas por carrera (pregunta 9 de `ENTREGA.md`) |
| **Proveedores de email intercambiables** | Interfaz `EmailProvider.send(to, subject, body, idempotency_key) → Accepted(id) / RetryLater(after) / Rejected(motivo) / ConfigError` en `infrastructure/email/`; `notificador.py` es la primera implementación y traduce sus códigos (202 / 5xx-timeout-red / 429+Retry-After / 400 / 401) a esos cuatro resultados. **La política de reintentos, el ritmo y la bandeja de salida viven fuera, en `application/`**, y no saben de HTTP. Proveedor elegido por nombre en settings (`EMAIL_PROVIDER`), con sus credenciales en entorno; la vista de configuración lo enseña, sin editarlo. Cada `Notification` guarda qué proveedor la envió (decidido 13/11) | Cliente del notificador llamado directamente desde la tarea | Cambiar de proveedor = una clase nueva y una variable de entorno, sin tocar reintentos ni pantallas. Si un proveedor futuro no tiene idempotencia, la protección contra duplicados sigue siendo nuestro estado en BD; el riesgo queda solo en el caso «timeout y no sabemos», y se documenta en su adaptador |
| **Aforo y lista de espera** | `Race.capacity` nullable (decidido 13/11: depende de la carrera; se pide al crearla). Al importar o dar de alta: si las confirmadas llegan al aforo, la inscripción queda `en_espera`, sin dorsal y con `waitlist_position` por orden de llegada (orden de importación y, dentro del fichero, de fila). **Sale de la lista** cuando hay hueco: una baja dada en la app o una subida de aforo → la primera en espera pasa a confirmada con el siguiente dorsal y queda pendiente de email. Todo bajo la carrera bloqueada | Aforo como bandera aparte; promoción por fecha de inscripción; reutilizar el dorsal de la baja | Las plataformas no mandan fecha de inscripción: el orden de llegada a nosotros es lo único medible. Reutilizar un dorsal ya impreso o comunicado confunde el día de la carrera |
| **Bajas** | Acción manual en la app (`status=baja`); el dorsal no se reutiliza; libera plaza para la lista de espera | Deducirlas de los listados | Ver «Reimportación» |
| **Ingesta en etapas, con un normalizador común** (decidido 13/11) | Cinco etapas, y solo la primera sabe de dónde viene el dato: **1. Origen** (subida de fichero hoy; API o SFTP mañana) → bytes y metadatos. **2. Lector de formato** (`infrastructure/sources/`: xlsx, csv; mañana JSON) → registros **en bruto** con su nº de línea, sin interpretar nada: la fecha del xlsx sigue siendo fecha de Excel y el teléfono, número. Codificación y separador se detectan, salvo que el canal los fije. **3. Mapeo de columnas** por canal: cabeceras normalizadas (minúsculas, sin tildes) más los alias de `ChannelColumn`. **4. Normalizador común** (`domain/normalize.py`, uno solo para todos): registro en bruto → `CanonicalRegistration` (nombres sin espacios sobrantes, email y `email_norm`, fecha desde texto con el formato del canal, desde fecha de Excel o desde `datetime`, teléfono como texto desde número o texto, talla en mayúsculas) **o** errores de forma («fecha no válida: 31/02/1990»). **5. Validación de negocio** (`domain/`: edad ≥ 16 el día de la carrera, talla permitida, email válido) y después el núcleo de inscribir (T4). **El alta de la tienda entra por la etapa 4** (el formulario es un registro en bruto más), así que las reglas son las mismas venga de donde venga | Un importador por canal; lectores que ya devuelven filas interpretadas; normalizar dentro de cada lector; mapeos en un campo JSON | Separar forma (4) de reglas (5) hace que un proveedor nuevo solo toque las etapas 1–3, normalmente con una fila en `Channel` y unos alias, sin código. Un formato nuevo es un lector; un transporte nuevo, un origen; las reglas no se duplican. El mapeo va en una tabla y no en `JSONField` para no depender del soporte de JSON de cada motor. Las tres fuentes de las muestras ya comparten columnas: lo que cambia es el formato y la codificación, y eso es configuración del canal |
| **Normalizador abierto** (decidido 17/11) | No es una lista de los casos de las muestras: es un **registro de reglas por campo** (`dict` campo → función) que se aplican igual en todas las fuentes. Cada regla devuelve un valor o una **incidencia tipada** (código, campo y valor en bruto), y **nunca lanza**: un tipo inesperado o una excepción interna se convierten en incidencia de esa fila, no tumban el fichero. **Limpieza común** de todo texto antes de cada regla: Unicode NFC, BOM, espacios de no separación y de ancho cero, saltos de línea dentro de la celda, espacios repetidos. **Reglas por campo**: *fecha* → prueba en orden fecha nativa (xlsx), número de serie de Excel y los `date_formats` del canal, y **no adivina** (`03/04/1990` con formato desconocido no se interpreta como mes/día; año de 2 cifras, rechazado: es una fecha de nacimiento); *email* → quita espacios, `mailto:` y `<…>`, normaliza a minúsculas; *teléfono* → texto libre, un número pasa a texto sin decimales; *talla* → mayúsculas y luego `ValueAlias` del canal o global; *nombres* → limpieza, sin cambiar mayúsculas (rompería «de la Fuente»). **Lo desconocido se agrupa en el informe**: «17 filas con talla `Única` (valor desconocido)», con el valor en bruto, para que la solución sea **configurar un alias o un formato de fecha, no tocar código**. Añadir un campo o una regla es una función en el registro | Un `if` por cada caso visto; adivinar formatos de fecha (`dateutil`); corregir nombres automáticamente; lanzar excepción en la primera fila rara | Las muestras solo enseñan lo que ha pasado; los errores nuevos llegarán con proveedores nuevos. Adivinar `03/04` da fechas mal y categorías mal sin avisar, que es el error del que se queja el cliente. Agrupar por valor convierte un informe de 300 líneas iguales en una decisión |
| **Tienda: alta en la app** | La tienda deja el Excel y da de alta en la app (decidido 13/11): formulario con las mismas validaciones del dominio; al escribir el email (o nombre + fecha) avisa **antes de guardar** «ya inscrita por Plataforma B, dorsal 17» y ofrece editar sus datos en vez de crear otra. Respeta aforo (avisa si va a lista de espera). El importador de CSV de tienda se mantiene para lo que ya está en el Excel | Seguir con el Excel; solo avisar al importar | Es la única forma de evitar el duplicado en origen. Desde una plataforma no se puede evitar (no pasan por nosotros): ahí queda la alerta del informe |
| **Datos personales** | Se tratan solo para gestionar la carrera. **Los logs no llevan emails ni teléfonos**: registran el id de la inscripción y la línea del fichero. Los ficheros subidos se guardan junto a su importación (sirven de rastro), con una pregunta abierta sobre cuánto tiempo. Consentimiento, política de privacidad, plazo de conservación y anonimización van como preguntas (10–13 de `ENTREGA.md`) | Registrar la fila completa en los logs; borrar o anonimizar automáticamente sin saber el plazo | Hasta 20.000 personas por carrera con email, teléfono y fecha de nacimiento: lo que vaya a un log acaba en sitios que nadie controla. Los plazos y la anonimización los decide el cliente, no la herramienta |
| **Filas inválidas** | No se guardan como inscripción; se guardan como `ImportIssue` con línea y motivo legible y se muestran tras importar | Guardarlas como inscripciones «inválidas» | Una inscripción sin fecha o sin email no puede tener categoría ni email: mezclarlas complica todo lo demás |
| **Búsqueda** | `?q=` sobre `search_text` (nombre y apellidos normalizados, sin tildes, en minúsculas) con `icontains`, o igualdad exacta si `q` es un número (dorsal). Paginada | `icontains` sobre los campos originales; búsqueda de texto completo | Que «garcia» encuentre «García» no puede depender de la collation del motor (SQL Server suele ser insensible a tildes; PostgreSQL y SQLite no). Texto completo es específico de cada motor |
| **Lector de xlsx** | `openpyxl` (nueva dependencia, `read_only=True`) | Leer el XML a mano; pandas | Es el estándar; pandas es enorme para leer 6 columnas |
| **Cliente HTTP del notificador** | `urllib` de la librería estándar, envuelto en `infrastructure/notifier.py` | requests / httpx | Una sola llamada POST; no justifica una dependencia |
| **Capas** | `domain/` (edad, categoría, validación de fila, normalización), `infrastructure/` (lectores de fichero, cliente del notificador), `application/` (importar, enviar), `api/` | Todo en vistas | Es la convención del esqueleto y deja el dominio testeable sin base de datos |

Nada de lo anterior depende de un motor: constraint condicional, `select_for_update`, `F()`, `bulk_create` con lotes
(mssql-django ya respeta el límite de 2.100 parámetros de SQL Server) e `icontains` sobre una columna normalizada.

---

## §5 · Alcance

Sin límite de tiempo (decidido 13/11): entra lo que hace falta para que las decisiones de arriba funcionen de punta a punta.

**Entra:**
1. Importar los tres formatos, en segundo plano, con progreso, en cola por carrera y con informe (altas, en espera, actualizadas, sin cambios, repetidas, ya inscritas con diferencias, rechazadas con motivo).
2. Reimportación idempotente con dorsales estables.
3. Categoría calculada y dorsal único por carrera, seguros con varios usuarios.
4. Duplicados: ya inscritos (sin segundo dorsal, con alerta) y posibles (marcados y enlazados).
5. Ingesta en etapas: origen → lector de formato → mapeo por canal → normalizador común → validación; canales configurables (formato, codificación, separador, formato de fecha, alias de columnas).
6. Alta en la app para la tienda, con aviso de «ya inscrita» antes de guardar.
7. Aforo por carrera y lista de espera; baja manual que promociona al siguiente.
7b. Ausencias en el listado completo marcadas para confirmar la baja; avisos y rechazos nuevos frente a los ya vistos.
8. Lista de inscripciones paginada con búsqueda por nombre, email o dorsal.
9. Emails de confirmación robustos (bandeja de salida, reintentos, `Retry-After`, `Idempotency-Key`, reanudación) detrás de una interfaz de proveedor.
10. Envío con botón y programado con beat; vista de configuración en BD (envío, plantilla, ritmo, reintentos, importaciones caídas).

**Después:** acciones sobre posibles duplicados («no es duplicado», «fusionar»); edición de inscripciones fuera del alta; exportar dorsales; integración por API/SFTP de una plataforma concreta.

**Fuera:** autenticación (fuera en el enunciado), y con ella saber qué usuario hizo cada cosa.
