# Tareas: inspector de huecos UW

Detalle y riesgos: [plan.md](plan.md). Spec:
[spec-clause-inspector.md](../docs/spec-clause-inspector.md).

Tests, desde la raíz de este repo:

```sh
python3 -m unittest tests.test_api_key tests.test_aspect tests.test_lora_fetch tests.test_clauses tests.test_catalog tests.test_inspector -v
```

## Phase 1 — semilla real

## Task 1: Expandir en `process` con la semilla ya resuelta

**Description:** Mover la expansión de `before_process` a `process`. En
`process_images_inner`, `get_fixed_seed`, `setup_prompts` y `p.all_seeds` ya
corrieron, así que cada prompt del lote tiene su semilla y el sorteo deja de
congelarse con `-1`.

**Acceptance criteria:**

- [ ] Con `seed: -1`, dos generaciones seguidas dan cláusulas distintas
- [ ] Con lote mayor que uno, cada imagen usa su propia semilla
- [ ] `p.main_prompt` queda igual a `p.all_prompts[0]`
- [ ] El tamaño y la descarga de LoRA siguen funcionando en el mismo hook
- [ ] El JSON de cláusulas se sigue guardando en los parámetros de la imagen

**Verification:**

- [ ] Tests pass: los cinco módulos actuales siguen en OK
- [ ] Manual check: el curl de la spec dos veces seguidas, con `seed: -1`, y comparar el texto y el `Seed:` del infotext

**Dependencies:** None

**Files likely touched:**

- `scripts/uw_wildcards.py`

**Estimated scope:** S

## Checkpoint: semilla

- [ ] Dos generaciones con `seed: -1` no repiten el texto
- [ ] Tests de unidad en OK
- [ ] Revisión humana antes de tocar Gradio

## Phase 2 — paquete del inspector

## Task 2: `trace` en el expansor

**Description:** `expand_with_overrides` acepta un `trace` opcional. Cuando llega, `_pick` anota el texto elegido por hueco, salvo los vacíos. Sin `trace` el comportamiento y el texto son los de hoy.

**Acceptance criteria:**

- [ ] El texto con `trace` es idéntico al de sin `trace`, para el mismo fixture
- [ ] El diccionario trae una entrada por hueco con texto
- [ ] Un hueco omitido no aparece en el diccionario
- [ ] El centinela de skip no sale en ningún valor

**Verification:**

- [ ] Tests pass: `python3 -m unittest tests.test_clauses -v`

**Dependencies:** None

**Files likely touched:**

- `forge_uw_wildcards/clauses.py`
- `tests/test_clauses.py`

**Estimated scope:** S

## Task 3: `collect_slots` y `resolve_seed`

**Description:** Módulo nuevo con las dos funciones puras que usará la UI. `collect_slots` devuelve el texto de cada hueco para una semilla, con los overrides aplicados. `resolve_seed` elige entre el número del tab y la última generación.

**Acceptance criteria:**

- [ ] Las 17 claves de `SLOT_LABELS` salen con texto, dado un router del fixture
- [ ] Dos llamadas con la misma semilla dan el mismo diccionario
- [ ] Un hueco fijado devuelve el texto fijado, no el sorteado
- [ ] `resolve_seed` con un número en el campo gana sobre la última generación
- [ ] `resolve_seed` con `-1` cae a la última; sin fuentes devuelve `None`

**Verification:**

- [ ] Tests pass: `python3 -m unittest tests.test_inspector -v`
- [ ] El módulo no importa `modules`

**Dependencies:** Task 2

**Files likely touched:**

- `forge_uw_wildcards/inspector.py`
- `tests/test_inspector.py`

**Estimated scope:** S

## Checkpoint: inspector

- [ ] `tests.test_inspector` en OK
- [ ] El texto con `trace` es idéntico al de sin `trace`
- [ ] Revisión humana antes de la UI

## Phase 3 — UI

## Task 4: Fila de vista previa y espejo de la semilla

**Description:** Botones **Ver lo generado** y **Vaciar**, una línea de estado y un espejo oculto del campo Seed del tab, conectado desde `show()` con `on_after_component`. El botón rellena los 17 campos sin tocar el JSON.

**Acceptance criteria:**

- [ ] **Ver lo generado** rellena las 17 cajas y nombra la semilla y su origen en la línea de estado
- [ ] Con `-1` usa la de la última generación y lo dice
- [ ] Con un número en el campo Seed, lo dice como campo, no como última generación
- [ ] Sin fuente, avisa y no rellena nada
- [ ] **Vaciar** deja las 17 cajas en blanco y el JSON intacto
- [ ] Con el acordeón apagado no se calcula nada
- [ ] Fijar tras la vista previa conserva el texto que apareció

**Verification:**

- [ ] Tests pass: los seis módulos en OK
- [ ] Manual check: elegir router, generar, **Ver lo generado**, fijar el pelo, generar con otra semilla

**Dependencies:** Task 1, Task 3

**Files likely touched:**

- `scripts/uw_wildcards.py`

**Estimated scope:** M

## Task 5: Comprobación manual en el WebUI

**Description:** Recorrer los criterios de éxito de la spec con el pack real y anotar lo que salga.

**Acceptance criteria:**

- [ ] Dos generaciones con `seed: -1` dan prompts distintos
- [ ] **Ver lo generado** con una semilla del tab da exactamente el texto de esa semilla
- [ ] Un hueco fijado sobrevive a un cambio de semilla y no arrastra a los demás
- [ ] El JSON de la imagen sigue permitiendo reconstruir router y overrides

**Verification:**

- [ ] Manual check: anotar semilla, texto y JSON en el resultado

**Dependencies:** Task 4

**Files likely touched:** ninguno

**Estimated scope:** S

## Checkpoint: Complete

- [ ] Criterios de éxito de la spec cumplidos
- [ ] Revisión humana
