# Implementation Plan: inspector de huecos UW

## Overview

Slice C sobre `docs/spec-clause-inspector.md`. Primero corrige que la expansión
ocurre cuando `p.seed` todavía vale `-1`, así que la semilla aleatoria congela el
sorteo. Con la semilla real en la mano, añade un botón **Ver lo generado** que
rellena los 17 campos con el texto que salió, para poder fijarlo con un clic.

Base: `main` en `2bee331`, rama `spec/clause-inspector` con la spec y nada de
código.

## Architecture Decisions

- La expansión se mueve de `before_process` a `process`. En `process`,
  `process_images_inner` ya llamó a `get_fixed_seed`, a `p.setup_prompts()` y
  rellenó `p.all_seeds`, así que cada prompt del lote tiene su semilla.
- No se resuelve la semilla a mano con `get_fixed_seed` desde `before_process`:
  el valor sorteado no sería el que usa el muestreador y la vista previa
  mentiría.
- La vista previa reutiliza el expansor con un `trace` opcional. Un segundo
  renderizador se desincroniza del primero.
- `resolve_seed` es una cadena de prioridad (espejo del tab → última
  generación), no una jerarquía de estrategias: hay dos fuentes.
- El espejo de la semilla se conecta desde `show()` con `on_after_component`,
  porque `apply_on_before_component_callbacks()` vacía las listas de cada script
  antes de que corra cualquier `ui()`.
- Nada se fija automáticamente. **Ver lo generado** solo rellena cajas.
- `p.main_prompt` se actualiza junto a `p.all_prompts[0]`, porque
  `setup_prompts()` lo fijó antes de la expansión.
- El tamaño se aplica en `process`, después de `sd_model.fix_dimensions`. El
  múltiplo configurado sigue mandando; si un modelo impone dimensiones
  propias, la ganancia de `fix_dimensions` se pierde. Se acepta.

## Dependency graph

```text
expansión en process (semilla real)
    └── trace en expand_with_overrides
            └── collect_slots + resolve_seed (paquete puro)
                    └── botones y espejo de semilla en la UI
                            └── comprobación manual en el WebUI
```

Todo lo que se puede testear sin Gradio vive en el paquete. La UI solo traduce.

## Task List

### Phase 1: semilla real

- [ ] Task 1: Expandir en `process` con la semilla ya resuelta

### Checkpoint: semilla

- [ ] Dos generaciones con `seed: -1` dan textos distintos
- [ ] Tests de unidad del paquete en OK
- [ ] Revisión humana antes de tocar la UI

### Phase 2: paquete del inspector

- [ ] Task 2: `trace` en el expansor
- [ ] Task 3: `collect_slots` y `resolve_seed`

### Checkpoint: inspector

- [ ] `tests.test_inspector` en OK
- [ ] El texto con `trace` es idéntico al de sin `trace`

### Phase 3: UI

- [ ] Task 4: Fila de vista previa y espejo de la semilla
- [ ] Task 5: Comprobación manual en el WebUI

### Checkpoint: Complete

- [ ] Los criterios de éxito de la spec se cumplen
- [ ] Revisión humana

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Mover la expansión a `process` rompe la descarga de LoRA o el tamaño | Alto | Las funciones del paquete no cambian: `render_prompts` sigue recibiendo prompts y semillas. Se comprueba con el mismo curl que documenta la spec y con los 40 tests existentes. |
| Forge cambia `txt2img_seed` / `img2img_seed` | Medio | El espejo es un adaptador: si no se conecta, el botón cae a la última generación y lo dice en la línea de estado. |
| El tamaño pierde `sd_model.fix_dimensions` | Bajo | Documentado en las decisiones. El múltiplo configurado sigue aplicándose. |
| Los 17 campos rellenados se confunden con huecos fijados | Medio | La spec lo dice explícitamente: la verdad es el JSON. El plan no añade ningún cambio visual al JSON. |
| «Ver lo generado» con un número en el campo Seed muestra una predicción, no algo ya generado | Medio | La línea de estado nombra el origen de la semilla, así que la etiqueta no promete de más. |

## Open Questions

Ninguna abierta. Las dos de la spec quedan resueltas: el botón se llama **Ver
lo generado** y no hay campo de semilla propio.
