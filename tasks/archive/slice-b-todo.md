# Tareas: UW Wildcards

Detalle, riesgos y orden: [plan.md](plan.md). Spec: [docs/spec.md](../docs/spec.md).

Tests, desde la raíz de este repo:

```sh
python3 -m unittest tests.test_api_key tests.test_aspect tests.test_lora_fetch tests.test_clauses tests.test_catalog -v
```

## Phase 0 — hecho

## Task 0: Slice A (aspecto, clave, descarga)

**Description:** Acordeón que quita `[W:H]`, resuelve la clave del browser y descarga las LoRA del manifiesto a `UWModularWildcards/`.

**Acceptance criteria:**

- [x] 15 tests OK en el commit `fc0b327`
- [ ] Una generación en Forge con el acordeón encendido no se ha comprobado

**Verification:**

- [x] Tests pass: `python3 -m unittest tests.test_api_key tests.test_aspect tests.test_lora_fetch -v`
- [ ] Manual check: Install from URL, activar el acordeón, prompt que termine en `[3:4]`

**Dependencies:** None

**Files likely touched:** ya en `main`

**Estimated scope:** M (hecho)

## Phase 1 — expansor

## Task 1: Fixture mínimo y test que falla

**Description:** Extraer un router, una plantilla y dos hojas del YAML del zip a `tests/fixtures/`, y un test que compare el texto con `expand_with_overrides` del zip. El test empieza en rojo.

**Acceptance criteria:**

- [x] El fixture no incluye el corpus entero ni miniaturas
- [x] El test llama al oráculo del zip y a `forge_uw_wildcards.clauses`, y falla porque el nuestro aún no existe
- [x] El fixture cabe en git (texto, pocos KB)

**Verification:**

- [x] Tests pass: el test nuevo falla por la razón esperada (módulo o función ausente), el resto sigue en OK

**Dependencies:** None

**Files likely touched:**

- `tests/fixtures/`
- `tests/test_clauses.py`

**Estimated scope:** S

## Task 2: Expandir router y plantilla

**Description:** Implementar la expansión de `__uw-krea2-nsfw/router/…__` y `__uw-krea2-nsfw/template/…__` con overrides de texto, hasta que el test de la task 1 quede en verde.

**Acceptance criteria:**

- [x] El texto del fixture coincide con el oráculo para la misma semilla y los mismos overrides
- [x] Un tag que no sea `uw-*` sale igual que entró
- [x] Sin red y sin importar `modules`

**Verification:**

- [x] Tests pass: `python3 -m unittest tests.test_clauses -v`

**Dependencies:** Task 1

**Files likely touched:**

- `forge_uw_wildcards/clauses.py`
- `tests/test_clauses.py`

**Estimated scope:** M

## Task 3: Semilla por hueco, pin, skip y regenerar

**Description:** Cada hueco tira con `hash(semilla, id, contador)`. Pin escribe el texto. Skip lo omite. Regenerar incrementa solo el contador de ese hueco.

**Acceptance criteria:**

- [x] Regenerar `lighting` no cambia `hair` ni `age`
- [x] Pin deja el mismo texto en una segunda expansión con otra semilla global
- [x] Skip quita esa cláusula

**Verification:**

- [x] Tests pass: `python3 -m unittest tests.test_clauses -v`

**Dependencies:** Task 2

**Files likely touched:**

- `forge_uw_wildcards/clauses.py`
- `tests/test_clauses.py`

**Estimated scope:** M

## Task 4: Limpieza de puntuación

**Description:** Portar la limpieza del motor 3.1.0 para que un skip no deje `BODY.,` ni comas dobles.

**Acceptance criteria:**

- [x] Un fixture con skip en medio de la frase no contiene `, .` ni `,,` ni una cláusula colgando con punto pegado al token anterior
- [x] Una frase sin skip no cambia de puntuación respecto al oráculo

**Verification:**

- [x] Tests pass: `python3 -m unittest tests.test_clauses -v`

**Dependencies:** Task 3

**Files likely touched:**

- `forge_uw_wildcards/clauses.py`
- `tests/test_clauses.py`

**Estimated scope:** S

## Checkpoint: Expansor

- [x] `tests.test_clauses` en OK
- [ ] Revisión humana antes de la UI

## Phase 2 — UI

## Task 5: Catálogo de nombres

**Description:** Leer routers y plantillas del directorio de wildcards del usuario y devolver la lista de tags. Sin miniaturas.

**Acceptance criteria:**

- [x] Un directorio fixture con un router y una plantilla produce esos dos tags
- [x] Un directorio vacío produce lista vacía, no una excepción
- [x] No se leen los `.catalog/` ni los PNG

**Verification:**

- [x] Tests pass: `python3 -m unittest tests.test_catalog -v`

**Dependencies:** Task 2

**Files likely touched:**

- `forge_uw_wildcards/catalog.py`
- `tests/test_clauses.py`

**Estimated scope:** S

## Task 6: Acordeón de cláusulas

**Description:** Desplegable de router o plantilla, un campo por cada uno de los 17 huecos, y botones pin / skip / regenerar que solo modifican el JSON oculto.

**Acceptance criteria:**

- [x] `before_process` sigue recibiendo el JSON, no 17 argumentos nuevos
- [x] Regenerar un hueco en la UI no pide red ni genera imagen
- [x] El acordeón apagado no cambia el prompt

**Verification:**

- [x] Tests pass: el paquete sigue en OK
- [x] Manual check: abrir txt2img, pin de un hueco, el JSON del campo oculto cambia y el resto no

**Dependencies:** Task 3, Task 5

**Files likely touched:**

- `scripts/uw_wildcards.py`
- `forge_uw_wildcards/state.py`

**Estimated scope:** M

## Task 7: Aplicar en la generación y guardar el extra

**Description:** Con el acordeón encendido, `before_process` sustituye el prompt por el texto expandido, aplica aspecto y descarga como en el slice A, y escribe el JSON en los parámetros de la imagen.

**Acceptance criteria:**

- [x] El prompt que ve el encoder no contiene `__uw-krea2-nsfw/` ni un `[W:H]` final
- [x] El extra permite reconstruir router y overrides
- [x] La longitud de `all_prompts` no cambia

**Verification:**

- [x] Tests pass: unidad del paquete
- [x] Manual check: una imagen en Forge cuyo PNG info trae el prompt expandido y el JSON

**Dependencies:** Task 4, Task 6

**Files likely touched:**

- `scripts/uw_wildcards.py`
- `forge_uw_wildcards/clauses.py`

**Estimated scope:** M

## Checkpoint: Generación

- [x] Tests de unidad en OK
- [x] Una generación manual revisada

## Phase 3 — ids que faltan

## Task 8: Completar version_id

**Description:** Rellenar el manifiesto con el `modelVersionId` de la ficha, no con la última versión del modelo. Alias: Realism Engine v3.0, Mrpopo, Snapchat Face Helper, y las dos de actos.

**Acceptance criteria:**

- [ ] Cada id nuevo tiene modelo, versión y URL de la ficha en el mensaje del commit
- [x] Un alias que siga en `null` sigue abortando la generación con su nombre
- [x] No se añade ningún peso al repo

**Verification:**

- [x] Tests pass: `python3 -m unittest tests.test_lora_fetch -v`
- [ ] Manual check: el tag de un alias recién pinado descarga a `UWModularWildcards/`

**Dependencies:** None (puede ir en paralelo con la phase 1)

**Files likely touched:**

- `forge_uw_wildcards/manifest.json`

**Estimated scope:** S

## Checkpoint: Complete

- [ ] Criterios del slice B en `docs/spec.md`
- [ ] Revisión humana
