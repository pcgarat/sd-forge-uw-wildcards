# Implementation Plan: UW Wildcards en Forge Neo

## Overview

Acordeón AlwaysVisible que aplica el pack UW Modular Wildcards v3 sobre Forge Neo: prosa por cláusulas, tamaño desde `[W:H]`, y descarga de las LoRA del manifiesto a `{lora_dir}/UWModularWildcards/`. El spec canónico es `docs/spec.md`. El slice A ya está en `main` (`fc0b327`). Este plan ordena lo que falta, sobre todo el slice B.

## Architecture Decisions

- La extensión es un repo aparte (`pcgarat/sd-forge-uw-wildcards`). Se instala desde la URL. `.no-seed` evita que docker-neo la copie.
- El expansor no llama a Impact Pack. Se reimplementa el contrato de `ComfyUI-WildcardClause/clause_expand.py` (zip en `uwModularV3/`) y se comprueba contra sus fixtures. No se copia el nodo de ComfyUI.
- Un solo JSON de overrides viaja a `before_process`. Pin, skip y regenerar editan ese JSON. Añadir un hueco no desplaza el infotext.
- La semilla es por hueco: `hash(semilla, id del hueco, contador)`. Regenerar uno no cambia los demás. No se re-tira en `process_before_every_sampling`.
- Los `__tags__` que no sean `uw-*` se dejan para sd-dynamic-prompts. `metadata.ini` ya dice `Before = sd-dynamic-prompts`.
- Las LoRA se quedan en el prompt, reescritas a `UWModularWildcards/…`. Sin id en el manifiesto no hay descarga.
- Los 17 huecos del motor, en este orden: wardrobe, environment, medium, lighting, treatment, hair, body, age, eye_color, nationality, skin, face, jewelry, skin_tone, hair_color, breast_size, butt_size. `subject` existe en el YAML como hoja, no como campo de la UI.

## Dependency graph

```text
manifiesto con version_id
    └── descarga al generar (slice A, hecho)

fixtures del zip (YAML mínimo + un caso de clause_expand)
    └── expansor puro (router, plantilla, overrides, semilla por hueco)
            └── limpieza de puntuación
                    └── acordeón: catálogo, JSON, pin / skip / regenerar
                            └── before_process escribe prompt + extra del PNG
```

El aspecto y la descarga ya no bloquean al expansor. El catálogo de nombres sale del mismo YAML que el expansor, así que va después del primer test de expansión.

## Task List

### Phase 0: Slice A (hecho)

- [x] Task 0: Acordeón, clave de API, marcador `[W:H]`, descarga a `UWModularWildcards/`
  - Hecho en `fc0b327`. 15 tests OK.
  - Pendiente de comprobación manual dentro de Forge (no hay WebUI en esta sesión).

### Phase 1: Expansor puro

- [x] Task 1: Fixture mínimo y test que falla
- [x] Task 2: Expandir router y plantilla con overrides
- [x] Task 3: Semilla por hueco, pin, skip y regenerar
- [x] Task 4: Limpieza de puntuación

### Checkpoint: Expansor

- [x] `python3 -m unittest tests.test_clauses -v` en OK
- [x] El mismo fixture produce el mismo texto que `expand_with_overrides` del zip
- [ ] Revisión humana antes de tocar Gradio

### Phase 2: UI y generación

- [x] Task 5: Catálogo de routers y plantillas
- [x] Task 6: Acordeón de cláusulas sobre el JSON
- [x] Task 7: `before_process` aplica el texto y guarda el extra

### Checkpoint: Generación

- [x] Tests de unidad del paquete en OK
- [x] Una generación manual en Forge con el acordeón encendido
- [ ] Revisión humana antes de seguir con ids o miniaturas

### Phase 3: LoRA que aún no tienen id

- [x] Task 8: Completar `version_id` del manifiesto

### Checkpoint: Complete

- [ ] Los criterios del slice B en `docs/spec.md` se cumplen
- [x] Ningún alias del manifiesto queda en `null` sin una nota de por qué

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| El expansor del zip depende de Impact para resolver `__tags__` | Alto | El test de la task 1 usa un YAML mínimo propio. Si un caso solo pasa llamando a Impact, se para y se pregunta. |
| Copiar `clause_expand.py` tal cual arrastra Comfy e Impact | Alto | Se reimplementa el contrato. El zip es el oráculo de los tests, no una dependencia. |
| SNOFS v1.3D es LoKR y Forge no lo aplica | Medio | La task 0 solo garantiza el fichero. Probar el loader es manual y no bloquea el expansor. |
| Un alias nuevo sin `version_id` aborta la generación si el prompt lo nombra | Medio | El manifiesto ya pincha las siete fichas. Un `null` que se añada después sigue abortando y nombra el alias. |
| Un batch no puede tener un ancho distinto por imagen | Bajo | El tamaño sale del primer prompt. Documentado en el spec. |

## Open Questions

- La task 8 pincha la versión que nombra la tabla del pack. Mrpopo 3214145 tiene dos LoRA; la descarga se queda con el fichero primario.
- Las miniaturas del catálogo (358 PNG) quedan fuera. El catálogo de la task 5 es solo nombres.
